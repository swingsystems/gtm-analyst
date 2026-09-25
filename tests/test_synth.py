from decimal import Decimal
from pathlib import Path

from gtm_analyst.synth.generate import generate
from gtm_analyst.synth.profile import load_profile

PROFILE = Path(__file__).parent.parent / "warehouse" / "seeds" / "profile.yaml"


def test_generation_is_deterministic():
    """Same profile, same seed, identical output. Ground truth cannot drift."""
    assert generate(load_profile(PROFILE), seed=42) == generate(load_profile(PROFILE), seed=42)


def test_different_seed_gives_different_data():
    a = generate(load_profile(PROFILE), seed=42)
    b = generate(load_profile(PROFILE), seed=43)
    assert a["raw_bookings"] != b["raw_bookings"]


def test_money_is_two_decimal_string_never_float():
    data = generate(load_profile(PROFILE), seed=42)
    for table, column in [("raw_bookings", "AMOUNT"), ("raw_billings", "AMOUNT"),
                          ("raw_revenue", "AMOUNT"), ("raw_quota", "QUOTA_AMOUNT")]:
        for row in data[table]:
            value = row[column]
            assert isinstance(value, str), f"{table}.{column} is {type(value)}, must be str"
            assert Decimal(value) == Decimal(value).quantize(Decimal("0.01"))
            assert len(value.split(".")[1]) == 2


def test_seeded_orphans_exist_and_are_recorded():
    """Anomalies are ground truth, so the generator must place AND report them."""
    data = generate(load_profile(PROFILE), seed=42)
    booked = {r["BOOKING_ID"] for r in data["raw_bookings"]}
    billed = {r["BOOKING_ID"] for r in data["raw_billings"]}
    revenued = {r["BOOKING_ID"] for r in data["raw_revenue"]}

    unbilled, unrecognised = booked - billed, booked - revenued
    assert unbilled and unrecognised

    manifest = data["_anomalies"]
    assert set(manifest["bookings_without_billing"]) == unbilled
    # Two disjoint reasons a booking has no revenue: seeded defect, and
    # intercompany elimination. The manifest must account for both exactly.
    assert set(manifest["bookings_without_revenue"]) <= unrecognised
    assert (set(manifest["bookings_without_revenue"])
            | set(manifest["bookings_intercompany"])) == unrecognised


def test_perpetual_recognises_once_subscription_recognises_monthly():
    data = generate(load_profile(PROFILE), seed=42)
    booking = {r["BOOKING_ID"]: r for r in data["raw_bookings"]}
    rows_for: dict[str, list] = {}
    for r in data["raw_revenue"]:
        rows_for.setdefault(r["BOOKING_ID"], []).append(r)

    perpetual = [b for b in rows_for if booking[b]["LICENSE_TYPE"] == "perpetual"]
    subscription = [b for b in rows_for if booking[b]["LICENSE_TYPE"] == "subscription"]
    assert perpetual and subscription

    for b in perpetual:
        assert len(rows_for[b]) == 1
        assert rows_for[b][0]["RECOGNITION_DATE"] == booking[b]["BOOKING_DATE"]
    for b in subscription:
        assert len(rows_for[b]) == int(booking[b]["TERM_MONTHS"])


def test_recognised_revenue_sums_exactly_to_booking_amount():
    """Rounding must not leak. The final period absorbs the remainder."""
    data = generate(load_profile(PROFILE), seed=42)
    amount = {r["BOOKING_ID"]: Decimal(r["AMOUNT"]) for r in data["raw_bookings"]}
    total: dict[str, Decimal] = {}
    for r in data["raw_revenue"]:
        total[r["BOOKING_ID"]] = total.get(r["BOOKING_ID"], Decimal("0")) + Decimal(r["AMOUNT"])  # noqa: FURB157
    for booking_id, recognised in total.items():
        assert recognised == amount[booking_id], f"{booking_id}: {recognised} != {amount[booking_id]}"


def test_billing_mirrors_bookings_except_seeded_gaps():
    data = generate(load_profile(PROFILE), seed=42)
    amount = {r["BOOKING_ID"]: Decimal(r["AMOUNT"]) for r in data["raw_bookings"]}
    unbilled = set(data["_anomalies"]["bookings_without_billing"])
    billed = {r["BOOKING_ID"]: Decimal(r["AMOUNT"]) for r in data["raw_billings"]}
    assert set(billed) == set(amount) - unbilled
    for booking_id, value in billed.items():
        assert value == amount[booking_id]


def test_null_segment_present():
    data = generate(load_profile(PROFILE), seed=42)
    assert any(r["SEGMENT"] == "" for r in data["raw_accounts"])


def test_quarter_boundary_booking_exists():
    data = generate(load_profile(PROFILE), seed=42)
    assert any(r["BOOKING_DATE"] == "2026-06-30" for r in data["raw_bookings"])


def test_territory_reassignment_mid_quarter():
    data = generate(load_profile(PROFILE), seed=42)
    per_territory: dict[str, list] = {}
    for r in data["raw_territory_assignments"]:
        per_territory.setdefault(r["TERRITORY_ID"], []).append(r)
    assert any(len(v) > 1 for v in per_territory.values())


def test_all_bookings_reference_real_accounts():
    data = generate(load_profile(PROFILE), seed=42)
    accounts = {r["ACCOUNT_ID"] for r in data["raw_accounts"]}
    assert all(r["ACCOUNT_ID"] in accounts for r in data["raw_bookings"])


def test_revenue_carries_account_and_region_for_persona_filtering():
    """Persona views filter on REGION and OWNER_REP_ID, so revenue must carry
    enough to be filtered without a join back to bookings."""
    data = generate(load_profile(PROFILE), seed=42)
    for row in data["raw_revenue"]:
        assert row["ACCOUNT_ID"]
        assert row["REGION"] in {"EMEA", "AMER", "APAC"}
        assert row["OWNER_REP_ID"]


def test_intercompany_bookings_recognise_no_revenue():
    """Intercompany sales eliminate on consolidation, so they never become
    external revenue. Without this, q005 compares ex-intercompany bookings
    against all-in revenue and the two can never tie."""
    data = generate(load_profile(PROFILE), seed=42)
    intercompany = {r["BOOKING_ID"] for r in data["raw_bookings"]
                    if r["IS_INTERCOMPANY"] == "true"}
    with_revenue = {r["BOOKING_ID"] for r in data["raw_revenue"]}
    assert intercompany, "profile must generate some intercompany bookings"
    assert not (intercompany & with_revenue)
    assert set(data["_anomalies"]["bookings_intercompany"]) == intercompany


def test_anomalies_land_inside_the_window_under_test():
    """Anomalies spread across the whole booking range mostly fall in quarters
    no question asks about, leaving q003 and q004 with no signal to measure."""
    profile = load_profile(PROFILE)
    start, end = (d.isoformat() for d in profile.anomalies.concentrate_window)
    data = generate(profile, seed=42)
    booking_date = {r["BOOKING_ID"]: r["BOOKING_DATE"] for r in data["raw_bookings"]}

    manifest = data["_anomalies"]
    for key in ("bookings_without_billing", "bookings_without_revenue"):
        placed = manifest[key]
        assert placed, f"{key} placed nothing"
        assert all(start <= booking_date[b] <= end for b in placed), \
            f"{key} placed outside the window under test"


def test_seeded_orphans_are_never_intercompany():
    """A seeded orphan is a defect. An intercompany booking correctly carries no
    revenue. Overlapping them would make q003 score a correct exclusion as a
    missed defect, and the question would stop measuring what it claims to."""
    data = generate(load_profile(PROFILE), seed=42)
    manifest = data["_anomalies"]
    assert not (set(manifest["bookings_without_revenue"])
                & set(manifest["bookings_intercompany"]))


def test_a_reps_accounts_are_all_in_one_region():
    """The rep persona must be a SUBSET of the regional one, or the frozen
    monotonic_nesting invariant (rep <= EMEA <= global) is simply false.

    Note this is about the rep's book of ACCOUNTS, not their territory history:
    a rep legitimately appears in two territories across time, because every rep
    is reassigned mid-quarter and that reassignment is the fan-out q011 exists
    to catch. Their accounts still belong to a single region.
    """
    data = generate(load_profile(PROFILE), seed=42)
    regions_per_rep: dict[str, set[str]] = {}
    for account in data["raw_accounts"]:
        regions_per_rep.setdefault(account["OWNER_REP_ID"], set()).add(account["REGION"])
    spanning = {rep: regions for rep, regions in regions_per_rep.items() if len(regions) > 1}
    assert not spanning, f"reps owning accounts across regions: {spanning}"


def test_boundary_bookings_are_visible_to_the_narrowest_persona():
    """A boundary booking on an account the restricted personas cannot see
    leaves their expected result empty, so the question asserts nothing for
    them while still appearing populated in the spec."""
    profile = load_profile(PROFILE)
    data = generate(profile, seed=42)
    narrowest = min(b["OWNER_REP_ID"] for b in data["raw_bookings"])
    for boundary in profile.anomalies.quarter_boundary_dates:
        on_date = [b for b in data["raw_bookings"]
                   if b["BOOKING_DATE"] == boundary.isoformat()]
        assert any(b["OWNER_REP_ID"] == narrowest for b in on_date), \
            f"no booking on {boundary} is visible to {narrowest}"


def test_territory_windows_are_half_open_and_cover_every_booking():
    """VALID_TO is the first instant NOT covered, so [VALID_FROM, VALID_TO)
    periods abut exactly. An inclusive end date leaves a one-day hole at every
    handover, and a booking landing there vanishes from any join that reads the
    window correctly -- which is a wrong_date_boundary failure hiding inside the
    question that tests for fan-out.
    """
    from datetime import date
    from itertools import pairwise

    data = generate(load_profile(PROFILE), seed=42)
    per_rep: dict[str, list] = {}
    for row in data["raw_territory_assignments"]:
        per_rep.setdefault(row["REP_ID"], []).append(row)

    for rep, rows in per_rep.items():
        windows = sorted((r["VALID_FROM"], r["VALID_TO"]) for r in rows)
        for (_, earlier_to), (later_from, _) in pairwise(windows):
            assert earlier_to <= later_from, f"{rep}: windows overlap"

    # Every Q3 booking must fall inside exactly one window for its own rep.
    territory_rows = data["raw_territory_assignments"]
    for booking in data["raw_bookings"]:
        booked = date.fromisoformat(booking["BOOKING_DATE"])
        if not (date(2026, 7, 1) <= booked <= date(2026, 9, 30)):
            continue
        matches = [
            t for t in territory_rows
            if t["REP_ID"] == booking["OWNER_REP_ID"]
            and date.fromisoformat(t["VALID_FROM"]) <= booked < date.fromisoformat(t["VALID_TO"])
        ]
        assert len(matches) == 1, (
            f"{booking['BOOKING_ID']} on {booking['BOOKING_DATE']} matched "
            f"{len(matches)} territory rows for {booking['OWNER_REP_ID']}"
        )
