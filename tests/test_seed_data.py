"""Assertions on the generated seed CSVs themselves.

test_synth.py covers the generator in memory; these tests cover the artefacts that
are actually committed and loaded into the warehouse, so a broken serialisation
step cannot pass unnoticed.
"""

import csv
import json
from decimal import Decimal
from pathlib import Path

SEEDS = Path(__file__).parent.parent / "warehouse" / "seeds"

MONETARY_COLUMNS = {
    "raw_bookings": "AMOUNT",
    "raw_billings": "AMOUNT",
    "raw_revenue": "AMOUNT",
    "raw_quota": "QUOTA_AMOUNT",
}


def read_csv(table: str) -> list[dict[str, str]]:
    with (SEEDS / f"{table}.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_every_seed_file_exists_and_is_non_empty():
    tables = ["raw_accounts", "raw_bookings", "raw_billings", "raw_revenue",
              "raw_territory_assignments", "raw_quota"]
    for table in tables:
        assert read_csv(table), f"{table}.csv is empty"


def test_money_columns_are_two_decimal_text_in_the_csvs():
    for table, column in MONETARY_COLUMNS.items():
        for row in read_csv(table):
            value = row[column]
            assert "." in value, f"{table}.{column}={value!r} has no decimal point"
            assert len(value.split(".")[1]) == 2, f"{table}.{column}={value!r} is not 2dp"
            assert Decimal(value) == Decimal(value).quantize(Decimal("0.01"))


def test_all_regions_present_in_accounts():
    regions = {row["REGION"] for row in read_csv("raw_accounts")}
    assert regions == {"EMEA", "AMER", "APAC"}


def test_at_least_one_empty_segment():
    assert any(row["SEGMENT"] == "" for row in read_csv("raw_accounts"))


def test_every_booking_references_a_real_account():
    accounts = {row["ACCOUNT_ID"] for row in read_csv("raw_accounts")}
    orphans = [r["BOOKING_ID"] for r in read_csv("raw_bookings") if r["ACCOUNT_ID"] not in accounts]
    assert orphans == []


def test_anomaly_manifest_matches_the_csv_gaps_exactly():
    manifest = json.loads((SEEDS / "_anomalies.json").read_text())
    booked = {row["BOOKING_ID"] for row in read_csv("raw_bookings")}
    billed = {row["BOOKING_ID"] for row in read_csv("raw_billings")}
    recognised = {row["BOOKING_ID"] for row in read_csv("raw_revenue")}

    assert set(manifest["bookings_without_billing"]) == booked - billed
    assert set(manifest["bookings_without_revenue"]) == booked - recognised
    assert booked - billed, "no unbilled bookings were planted"
    assert booked - recognised, "no unrecognised bookings were planted"


def test_billing_amounts_match_their_booking():
    amount = {row["BOOKING_ID"]: row["AMOUNT"] for row in read_csv("raw_bookings")}
    for row in read_csv("raw_billings"):
        assert row["AMOUNT"] == amount[row["BOOKING_ID"]]
