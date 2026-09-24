"""The committed contracts must load and must describe the real warehouse."""
from pathlib import Path

import pytest

from gaa.semantic.loader import load_contracts

CONTRACTS = Path(__file__).parent.parent / "semantic" / "contracts"

# Columns that actually exist on each persona view.
VIEW_COLUMNS = {
    "V_BOOKINGS": {"BOOKING_ID", "ACCOUNT_ID", "BOOKING_DATE", "FISCAL_QUARTER", "REGION",
                   "OWNER_REP_ID", "AMOUNT", "LICENSE_TYPE", "TERM_MONTHS", "IS_INTERCOMPANY"},
    "V_BILLINGS": {"BILLING_ID", "BOOKING_ID", "ACCOUNT_ID", "INVOICE_DATE", "FISCAL_QUARTER",
                   "REGION", "OWNER_REP_ID", "AMOUNT"},
    "V_REVENUE": {"REVENUE_ID", "BOOKING_ID", "ACCOUNT_ID", "RECOGNITION_DATE", "FISCAL_QUARTER",
                  "REGION", "OWNER_REP_ID", "LICENSE_TYPE", "AMOUNT"},
    "V_ACCOUNT": {"ACCOUNT_ID", "ACCOUNT_NAME", "REGION", "SEGMENT", "OWNER_REP_ID"},
}


@pytest.fixture(scope="module")
def contracts():
    return load_contracts(CONTRACTS)


def test_the_expected_metrics_exist(contracts):
    assert set(contracts.metrics) == {
        "bookings_amount@1", "revenue_amount@1", "billings_amount@1",
        "booking_count@1", "account_count@1",
    }


def test_every_table_is_unqualified(contracts):
    """A qualified name would defeat per-persona schema resolution outright."""
    for key, contract in contracts.metrics.items():
        assert "." not in contract.table, key
        assert contract.table in VIEW_COLUMNS, f"{key}: unknown view {contract.table}"


def test_every_referenced_column_exists_on_its_view(contracts):
    """A contract naming a column the view does not have fails at query time
    with a Snowflake error, long after the mistake was made."""
    for key, contract in contracts.metrics.items():
        columns = VIEW_COLUMNS[contract.table]
        assert contract.measure.column in columns or contract.measure.column == "*", key
        assert contract.period_column in columns, f"{key}: period {contract.period_column}"
        for dim in contract.dimensions:
            assert dim.column in columns, f"{key}: dimension {dim.column}"
        for filt in contract.default_filters:
            assert filt.column in columns, f"{key}: filter {filt.column}"


def test_every_contract_has_an_owner_and_a_real_description(contracts):
    """An unowned metric is one nobody will correct when it drifts."""
    for key, contract in contracts.metrics.items():
        assert contract.owner, key
        assert len(contract.description) > 30, f"{key}: description is too thin to be useful"


def test_bookings_exclude_intercompany_by_default(contracts):
    bookings = contracts.metrics["bookings_amount@1"]
    filters = {(f.column, f.op.value, f.value) for f in bookings.default_filters}
    assert ("IS_INTERCOMPANY", "eq", "false") in filters


def test_revenue_has_no_intercompany_filter(contracts):
    """Intercompany bookings recognise no revenue at all, so filtering here
    would be redundant and would imply the opposite about the data."""
    revenue = contracts.metrics["revenue_amount@1"]
    assert not any(f.column == "IS_INTERCOMPANY" for f in revenue.default_filters)


def test_segment_dimensions_preserve_nulls(contracts):
    """SEGMENT is nullable by design and a NULL segment must survive
    aggregation, or totals silently stop reconciling."""
    for key, contract in contracts.metrics.items():
        if any(d.column == "SEGMENT" for d in contract.dimensions):
            assert contract.null_policy == "preserve", key


def test_count_metrics_use_a_counting_aggregation(contracts):
    for key in ("booking_count@1", "account_count@1"):
        assert contracts.metrics[key].measure.aggregation.value in {"count", "count_distinct"}


def test_amount_metrics_sum_a_money_column(contracts):
    for key in ("bookings_amount@1", "revenue_amount@1", "billings_amount@1"):
        contract = contracts.metrics[key]
        assert contract.measure.aggregation.value == "sum"
        assert contract.measure.column == "AMOUNT"
