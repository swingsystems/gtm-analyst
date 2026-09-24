import pytest
from pydantic import ValidationError

from gaa.semantic.models import Aggregation, Dimension, Measure, MetricContract


def _contract(**overrides):
    base = dict(  # noqa: C408 - kwargs form keeps the override helper readable
        name="bookings_amount", version=1, description="Signed booking value",
        owner="sales-ops", table="V_BOOKINGS", grain="booking",
        measure=Measure(column="AMOUNT", aggregation=Aggregation.SUM),
        dimensions=[Dimension(name="region", column="REGION", description="Account region")],
        default_filters=[{"column": "IS_INTERCOMPANY", "op": "eq", "value": "false"}],
        null_policy="preserve", period_column="FISCAL_QUARTER",
    )
    base.update(overrides)
    return MetricContract(**base)


def test_contract_builds():
    c = _contract()
    assert c.measure.aggregation is Aggregation.SUM
    assert c.dimensions[0].column == "REGION"
    assert c.default_filters[0].column == "IS_INTERCOMPANY"


def test_measure_rejects_an_unknown_aggregation():
    with pytest.raises(ValidationError):
        Measure(column="AMOUNT", aggregation="median")


def test_column_names_must_be_plain_identifiers():
    """A column is interpolated into SQL as an identifier. Anything that is not
    a bare identifier is an injection vector, so it is rejected at the schema."""
    for bad in ["AMOUNT; DROP TABLE X", "A B", "A-B", "SUM(A)", "", "A'B", "A.B"]:
        with pytest.raises(ValidationError):
            Measure(column=bad, aggregation=Aggregation.SUM)


def test_table_must_be_unqualified():
    """Qualified names would defeat per-persona schema resolution outright:
    reference SQL and contracts both rely on the session default schema."""
    with pytest.raises(ValidationError):
        _contract(table="GAA.FINANCE.V_BOOKINGS")


def test_filter_op_is_closed():
    with pytest.raises(ValidationError):
        _contract(default_filters=[{"column": "X", "op": "regexp", "value": "y"}])


def test_null_policy_is_closed():
    with pytest.raises(ValidationError):
        _contract(null_policy="whatever")


def test_contract_rejects_unknown_fields():
    """extra=forbid: a contract carrying a 'sql' key must fail loudly rather
    than be silently ignored, because silence is how SQL gets into a schema
    that promises it cannot."""
    with pytest.raises(ValidationError):
        _contract(sql="SELECT 1")


def test_dimension_columns_are_validated_too():
    with pytest.raises(ValidationError):
        _contract(dimensions=[Dimension(name="r", column="REGION; --", description="d")])


def test_filter_values_may_be_arbitrary_strings():
    """Values are NOT identifiers — they bind as parameters, so a value that
    looks like SQL is harmless and must be allowed through. Rejecting it here
    would give a false sense that the schema is the injection defence, when the
    compiler's parameter binding is."""
    c = _contract(default_filters=[{"column": "REGION", "op": "eq",
                                    "value": "'; DROP TABLE X --"}])
    assert c.default_filters[0].value == "'; DROP TABLE X --"
