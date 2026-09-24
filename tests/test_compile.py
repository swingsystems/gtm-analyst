"""The compiler is where caller-supplied values become SQL.

Everything upstream validates identifiers. Values are deliberately NOT
validated, because the defence is parameter binding rather than sanitising --
so these tests exist to prove the binding actually happens.
"""
import pytest

from gaa.semantic.compile import CompileError, QueryRequest, compile_query
from gaa.semantic.loader import load_contracts
from pathlib import Path

CONTRACTS = load_contracts(Path(__file__).parent.parent / "semantic" / "contracts")


def _req(**kw):
    base = dict(metric="bookings_amount@1", dimensions=["region"], filters=[], period="2026-Q3")
    base.update(kw)
    return QueryRequest(**base)


def test_compiles_a_simple_grouped_query():
    q = compile_query(CONTRACTS, _req())
    assert "SUM(AMOUNT)" in q.sql
    assert "GROUP BY" in q.sql
    assert "V_BOOKINGS" in q.sql
    assert q.metrics_used == ["bookings_amount@1"]


def test_the_period_binds_as_a_parameter_not_as_text():
    q = compile_query(CONTRACTS, _req(period="2026-Q3"))
    assert "2026-Q3" not in q.sql
    assert "2026-Q3" in q.params


def test_a_malicious_filter_value_never_reaches_the_sql():
    """The single most important test in this module. A value that looks like
    SQL must appear in params and never in the statement."""
    attack = "'; DROP TABLE GAA.MARTS.FCT_BOOKINGS; --"
    q = compile_query(CONTRACTS, _req(
        filters=[{"column": "REGION", "op": "eq", "value": attack}]))
    assert attack not in q.sql
    assert attack in q.params
    assert "DROP" not in q.sql.upper()


def test_a_malicious_period_never_reaches_the_sql():
    attack = "2026-Q3' OR '1'='1"
    q = compile_query(CONTRACTS, _req(period=attack))
    assert attack not in q.sql
    assert attack in q.params


def test_an_undeclared_dimension_is_refused_by_name():
    with pytest.raises(CompileError, match="segment"):
        compile_query(CONTRACTS, _req(dimensions=["segment"]))


def test_an_undeclared_filter_column_is_refused():
    """A filter on a column the contract does not declare would let a caller
    reach any column on the view, which is the contract's whole point."""
    with pytest.raises(CompileError, match="OWNER_REP_ID"):
        compile_query(CONTRACTS, _req(
            filters=[{"column": "OWNER_REP_ID", "op": "eq", "value": "REP001"}]))


def test_an_unknown_metric_is_refused():
    with pytest.raises(CompileError, match="nonexistent_metric"):
        compile_query(CONTRACTS, _req(metric="nonexistent_metric@1"))


def test_default_filters_are_applied_and_bound():
    q = compile_query(CONTRACTS, _req())
    assert "IS_INTERCOMPANY" in q.sql
    assert "false" in q.params


def test_request_filters_combine_with_defaults_using_and():
    q = compile_query(CONTRACTS, _req(
        filters=[{"column": "REGION", "op": "eq", "value": "EMEA"}]))
    assert q.sql.upper().count(" AND ") >= 2  # period + default + request
    assert "EMEA" in q.params and "false" in q.params


def test_null_preserving_dimensions_coalesce_rather_than_drop():
    """SEGMENT is nullable by design. A NULL group must survive aggregation or
    totals silently stop reconciling -- the null_segment_dropped category."""
    q = compile_query(CONTRACTS, QueryRequest(
        metric="revenue_amount@1", dimensions=["segment"], filters=[], period="2026-Q3"))
    assert "COALESCE" in q.sql.upper()


def test_the_generated_sql_is_unqualified():
    """A qualified name would defeat per-persona schema resolution."""
    q = compile_query(CONTRACTS, _req())
    assert "GAA." not in q.sql.upper()


def test_lineage_names_the_view_and_the_metric_version():
    q = compile_query(CONTRACTS, _req())
    assert "V_BOOKINGS" in q.lineage
    assert q.metrics_used == ["bookings_amount@1"]


def test_in_operator_binds_every_element_separately():
    q = compile_query(CONTRACTS, _req(
        filters=[{"column": "REGION", "op": "in", "value": "EMEA,AMER"}]))
    assert "EMEA" in q.params and "AMER" in q.params
    assert "EMEA,AMER" not in q.sql


def test_the_statement_is_a_single_select():
    """Whatever the request, the output must be one SELECT. Anything else means
    a value escaped into statement position."""
    from gaa.spec.sql import sql_statements

    q = compile_query(CONTRACTS, _req(
        filters=[{"column": "REGION", "op": "eq", "value": "x'; DELETE FROM y; --"}]))
    statements = sql_statements(q.sql)
    assert len(statements) == 1
    assert statements[0].upper().startswith("SELECT")
