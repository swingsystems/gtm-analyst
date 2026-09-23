from decimal import Decimal
from pathlib import Path

from gaa.synth.generate import generate
from gaa.synth.profile import load_profile

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
    assert set(manifest["bookings_without_revenue"]) == unrecognised


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
