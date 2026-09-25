"""Deterministic synthetic warehouse generation driven by a dataset profile.

Determinism is a correctness property here, not a convenience: the generated data
is the ground truth an evaluation is scored against. Same profile plus same seed
must yield byte-identical output, so this module uses a local ``random.Random``
only, never the module-level ``random`` state, and never reads the wall clock.

All money is computed in integer cents and rendered as a 2-decimal string. No
monetary value is ever a float at any point.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from gtm_analyst.synth.profile import AccountsProfile, DatasetProfile

CENTS = Decimal("0.01")

Row = dict[str, str]
Dataset = dict[str, list]


def _money(cents: int) -> str:
    """Render integer cents as a string with exactly two decimal places."""
    return str((Decimal(cents) / 100).quantize(CENTS))


def _add_months(start: date, months: int) -> date:
    """Advance a date by whole months, clamping to the end of the target month."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    """Pick a key in proportion to its weight, using a stable key ordering."""
    roll = rng.random()
    cumulative = 0.0
    keys = sorted(weights)
    for key in keys:
        cumulative += weights[key]
        if roll < cumulative:
            return key
    return keys[-1]


def _pick_every_nth(ids: list[str], count: int, offset_fraction: float) -> list[str]:
    """Select ``count`` ids by even stride from a sorted list.

    Deterministic by construction and independent of the RNG stream, so adding a
    generation step upstream cannot silently move which rows are anomalous.
    """
    if count <= 0 or not ids:
        return []
    stride = max(1, len(ids) // count)
    offset = int(stride * offset_fraction)
    picked = [ids[min(offset + i * stride, len(ids) - 1)] for i in range(count)]
    return sorted(dict.fromkeys(picked))


def _quarters(year: int) -> list[tuple[str, date, date]]:
    bounds = [
        (f"{year}-Q1", date(year, 1, 1), date(year, 3, 31)),
        (f"{year}-Q2", date(year, 4, 1), date(year, 6, 30)),
        (f"{year}-Q3", date(year, 7, 1), date(year, 9, 30)),
        (f"{year}-Q4", date(year, 10, 1), date(year, 12, 31)),
    ]
    return bounds


def _reps_by_region(shape: "AccountsProfile") -> dict[str, list[int]]:
    """Reps are assigned to regions the same way territories are, so that an
    account's owner always belongs to the account's region.

    Without this, a rep's book of business spans regions while their territory
    does not, and the rep persona stops being a subset of the regional one --
    which contradicts the monotonic_nesting invariant and makes the persona
    hierarchy incoherent.
    """
    mapping: dict[str, list[int]] = {region: [] for region in shape.regions}
    for rep in range(1, shape.reps + 1):
        mapping[shape.regions[(rep - 1) % len(shape.regions)]].append(rep)
    return mapping


def _generate_accounts(profile: DatasetProfile, rng: random.Random) -> list[Row]:
    accounts: list[Row] = []
    shape = profile.accounts
    reps_for = _reps_by_region(shape)
    for index in range(1, shape.count + 1):
        region = shape.regions[rng.randrange(len(shape.regions))]
        segment = shape.segments[rng.randrange(len(shape.segments))]
        candidates = reps_for[region]
        rep = candidates[rng.randrange(len(candidates))]
        accounts.append(
            {
                "ACCOUNT_ID": f"ACC{index:05d}",
                "ACCOUNT_NAME": f"Account {index:05d}",
                "REGION": region,
                "SEGMENT": segment,
                "OWNER_REP_ID": f"REP{rep:03d}",
                "CREATED_DATE": (
                    date(2024, 1, 1) + timedelta(days=rng.randrange(0, 730))
                ).isoformat(),
            }
        )
    # Guarantee the profile's declared shapes are all actually represented.
    for offset, segment in enumerate(shape.segments):
        accounts[offset % len(accounts)]["SEGMENT"] = segment
    for offset, region in enumerate(shape.regions):
        account = accounts[-(offset + 1)]
        account["REGION"] = region
        # Re-home the owner as well, or forcing a region would recreate exactly
        # the cross-region ownership this function exists to prevent.
        account["OWNER_REP_ID"] = f"REP{reps_for[region][0]:03d}"
    return accounts


def _generate_bookings(
    profile: DatasetProfile, accounts: list[Row], rng: random.Random
) -> list[Row]:
    shape = profile.bookings
    start, end = shape.window
    span = (end - start).days
    low_amount, high_amount = shape.amount_range

    bookings: list[Row] = []
    for account in accounts:
        for _ in range(rng.randint(*shape.per_account)):
            booking_date = start + timedelta(days=rng.randrange(span + 1))
            cents = rng.randrange(low_amount * 100, high_amount * 100 + 1)
            license_type = _weighted_choice(rng, shape.license_split)
            term = (
                shape.subscription_terms[rng.randrange(len(shape.subscription_terms))]
                if license_type == "subscription"
                else 0
            )
            bookings.append(
                {
                    "BOOKING_ID": "",
                    "ACCOUNT_ID": account["ACCOUNT_ID"],
                    "BOOKING_DATE": booking_date.isoformat(),
                    "AMOUNT": _money(cents),
                    "CURRENCY": "USD",
                    "LICENSE_TYPE": license_type,
                    "TERM_MONTHS": str(term),
                    "REGION": account["REGION"],
                    "SEGMENT": account["SEGMENT"],
                    "OWNER_REP_ID": account["OWNER_REP_ID"],
                    "ACCOUNT_NAME": account["ACCOUNT_NAME"],
                    "IS_INTERCOMPANY": "false",
                }
            )

    for index, booking in enumerate(bookings, start=1):
        booking["BOOKING_ID"] = f"BK{index:06d}"
        if index % shape.intercompany_every == 0:
            booking["IS_INTERCOMPANY"] = "true"

    # Force a booking onto each declared quarter boundary so period-edge questions
    # have something to catch. Done before revenue so schedules follow the new date.
    # Place each boundary booking on an account the MOST restricted persona can
    # see. Landing them anywhere else leaves the restricted personas with an
    # empty expected result, so two thirds of the question's matrix would assert
    # nothing while still looking populated.
    narrowest_owner = min(b["OWNER_REP_ID"] for b in bookings)
    visible_to_all = [b for b in bookings if b["OWNER_REP_ID"] == narrowest_owner]
    for offset, boundary in enumerate(profile.anomalies.quarter_boundary_dates):
        target = visible_to_all[offset % len(visible_to_all)] if visible_to_all else bookings[offset]
        target["BOOKING_DATE"] = boundary.isoformat()
    return bookings


def _generate_billings(
    profile: DatasetProfile, bookings: list[Row], unbilled: set[str], rng: random.Random
) -> list[Row]:
    low_lag, high_lag = profile.billings.lag_days
    billings: list[Row] = []
    for booking in bookings:
        lag = rng.randint(low_lag, high_lag)
        if booking["BOOKING_ID"] in unbilled:
            continue
        invoice_date = date.fromisoformat(booking["BOOKING_DATE"]) + timedelta(days=lag)
        billings.append(
            {
                "BILLING_ID": f"BL{len(billings) + 1:06d}",
                "BOOKING_ID": booking["BOOKING_ID"],
                "ACCOUNT_ID": booking["ACCOUNT_ID"],
                "INVOICE_DATE": invoice_date.isoformat(),
                "AMOUNT": booking["AMOUNT"],
                "CURRENCY": booking["CURRENCY"],
                "REGION": booking["REGION"],
                "OWNER_REP_ID": booking["OWNER_REP_ID"],
            }
        )
    return billings


def _generate_revenue(bookings: list[Row], unrecognised: set[str]) -> list[Row]:
    """Recognise each booking: perpetual once, subscription monthly over its term.

    Cents are split evenly and the final period absorbs the remainder, so the
    schedule always sums back to the booking amount exactly.

    Intercompany bookings recognise NOTHING. A sale from one entity of a group to
    another is eliminated on consolidation, so it never becomes external revenue.
    Without this, recognised revenue would include intercompany while reported
    bookings exclude it, and the two could never be reconciled.
    """
    revenue: list[Row] = []
    for booking in bookings:
        if booking["BOOKING_ID"] in unrecognised:
            continue
        if booking["IS_INTERCOMPANY"] == "true":
            continue
        booking_date = date.fromisoformat(booking["BOOKING_DATE"])
        total_cents = int((Decimal(booking["AMOUNT"]) * 100).to_integral_value())
        periods = int(booking["TERM_MONTHS"]) if booking["LICENSE_TYPE"] == "subscription" else 1
        periods = max(periods, 1)
        per_period = total_cents // periods
        for period in range(periods):
            cents = per_period if period < periods - 1 else total_cents - per_period * (periods - 1)
            revenue.append(
                {
                    "REVENUE_ID": f"RV{len(revenue) + 1:07d}",
                    "BOOKING_ID": booking["BOOKING_ID"],
                    "ACCOUNT_ID": booking["ACCOUNT_ID"],
                    "RECOGNITION_DATE": _add_months(booking_date, period).isoformat(),
                    "AMOUNT": _money(cents),
                    "CURRENCY": booking["CURRENCY"],
                    "LICENSE_TYPE": booking["LICENSE_TYPE"],
                    "REGION": booking["REGION"],
                    "OWNER_REP_ID": booking["OWNER_REP_ID"],
                    "SEGMENT": booking["SEGMENT"],
                    "ACCOUNT_NAME": booking["ACCOUNT_NAME"],
                }
            )
    return revenue


def _generate_territories(profile: DatasetProfile, rng: random.Random) -> list[Row]:
    """Every rep owns a territory that is reassigned mid-year, effective-dated."""
    shape = profile.accounts
    start, end = profile.bookings.window
    split = profile.anomalies.territory_reassignment_date
    rows: list[Row] = []
    for index in range(1, shape.reps + 1):
        territory_id = f"TER{index:03d}"
        successor = index % shape.reps + 1
        # Same rule _reps_by_region uses when choosing account owners. Both must
        # agree or a rep ends up owning accounts outside their own territory.
        region = shape.regions[(index - 1) % len(shape.regions)]
        rows.append(
            {
                "TERRITORY_ID": territory_id,
                "REP_ID": f"REP{index:03d}",
                "REGION": region,
                "VALID_FROM": start.isoformat(),
                # HALF-OPEN: VALID_TO is the first instant NOT covered, so the
                # two periods abut exactly with no gap and no overlap. The
                # reference SQL reads them as [VALID_FROM, VALID_TO), and an
                # inclusive end date here would silently drop every booking
                # landing on a boundary -- which it did, losing 180,848.13.
                "VALID_TO": split.isoformat(),
            }
        )
        rows.append(
            {
                "TERRITORY_ID": territory_id,
                "REP_ID": f"REP{successor:03d}",
                "REGION": region,
                "VALID_FROM": split.isoformat(),
                "VALID_TO": (end + timedelta(days=1)).isoformat(),
            }
        )
    return rows


def _generate_quota(profile: DatasetProfile, rng: random.Random) -> list[Row]:
    year = profile.bookings.window[0].year
    rows: list[Row] = []
    for index in range(1, profile.accounts.reps + 1):
        for quarter, valid_from, valid_to in _quarters(year):
            cents = rng.randrange(200_000_00, 900_000_00 + 1, 1_000_00)
            rows.append(
                {
                    "QUOTA_ID": f"QT{len(rows) + 1:05d}",
                    "REP_ID": f"REP{index:03d}",
                    "FISCAL_YEAR": str(year),
                    "FISCAL_QUARTER": quarter,
                    "QUOTA_AMOUNT": _money(cents),
                    "CURRENCY": "USD",
                    "VALID_FROM": valid_from.isoformat(),
                    "VALID_TO": valid_to.isoformat(),
                }
            )
    return rows


def generate(profile: DatasetProfile, seed: int) -> Dataset:
    """Generate a complete synthetic warehouse plus its anomaly manifest.

    The manifest is ground truth: anomalies are placed deterministically and
    reported, so an evaluation can score an agent against what was actually planted.
    """
    rng = random.Random(seed)

    accounts = _generate_accounts(profile, rng)
    bookings = _generate_bookings(profile, accounts, rng)

    booking_ids = sorted(booking["BOOKING_ID"] for booking in bookings)

    # Anomalies are drawn from inside the window under test when one is declared.
    # Spread across the full booking range they mostly fall in quarters no
    # question asks about, so the reconciliation questions measure almost nothing.
    window = profile.anomalies.concentrate_window
    if window:
        start, end = window[0].isoformat(), window[1].isoformat()
        candidates = sorted(
            b["BOOKING_ID"] for b in bookings if start <= b["BOOKING_DATE"] <= end
        )
    else:
        candidates = booking_ids

    # A seeded orphan must be a DEFECT, never a booking that correctly carries no
    # revenue. Intercompany bookings already recognise nothing, so seeding one as
    # an orphan too would make the defect indistinguishable from the exclusion and
    # q003 would score a correct answer as a miss.
    intercompany_ids = {b["BOOKING_ID"] for b in bookings if b["IS_INTERCOMPANY"] == "true"}
    revenue_candidates = [b for b in candidates if b not in intercompany_ids]

    unbilled = _pick_every_nth(candidates, profile.anomalies.bookings_without_billing, 0.0)
    unrecognised = _pick_every_nth(
        revenue_candidates, profile.anomalies.bookings_without_revenue, 0.5
    )

    intercompany = sorted(b["BOOKING_ID"] for b in bookings if b["IS_INTERCOMPANY"] == "true")

    billings = _generate_billings(profile, bookings, set(unbilled), rng)
    revenue = _generate_revenue(bookings, set(unrecognised))
    territories = _generate_territories(profile, rng)
    quota = _generate_quota(profile, rng)

    return {
        "raw_accounts": accounts,
        "raw_bookings": bookings,
        "raw_billings": billings,
        "raw_revenue": revenue,
        "raw_territory_assignments": territories,
        "raw_quota": quota,
        "_anomalies": {
            "bookings_without_billing": unbilled,
            "bookings_without_revenue": unrecognised,
            # Intercompany bookings also carry no revenue, by consolidation rather
            # than by defect. Recorded separately so the expected answer to "which
            # bookings have no revenue" is explicit about containing both, and the
            # seeded-orphan signal is not silently conflated with correct exclusion.
            "bookings_intercompany": intercompany,
        },
    }
