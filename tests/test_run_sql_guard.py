"""The unconstrained comparison arm.

This exists so the experiment has something to measure against, which makes its
permissiveness a requirement rather than an oversight. A free-SQL arm that is
quietly hobbled -- no CTEs, no joins, no window functions -- would make the
contracts look good by handicapping the alternative, and the result would be
worthless.

What it is NOT free to do is leave read-only territory. The warehouse boundary
still holds because it executes as the persona; this guard is a second layer,
not the only one.
"""
import json
import os
from pathlib import Path

import pytest
from snowflake.connector.errors import DatabaseError, ProgrammingError

from gtm_analyst.mcp.tools import ToolError, ToolSurface
from gtm_analyst.spec.loader import load_spec

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
CONTRACTS = Path(__file__).parent.parent / "semantic" / "contracts"

live = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)


def _surface(persona="FINANCE_GLOBAL", audit_path=None):
    return ToolSurface(SPEC.personas[persona], CONTRACTS, audit_path=audit_path)


# ----------------------------------------------------- it must stay permissive


@live
@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM V_BOOKINGS",
    "WITH q AS (SELECT * FROM V_BOOKINGS) SELECT COUNT(*) FROM q",
    "SELECT b.REGION, SUM(b.AMOUNT) FROM V_BOOKINGS b GROUP BY b.REGION",
    "SELECT REGION, SUM(AMOUNT) OVER (PARTITION BY REGION) FROM V_BOOKINGS LIMIT 5",
    "SELECT b.BOOKING_ID FROM V_BOOKINGS b LEFT JOIN V_REVENUE r ON r.BOOKING_ID = b.BOOKING_ID WHERE r.BOOKING_ID IS NULL",
    "-- a leading comment\nSELECT 1 AS X",
])
def test_legitimate_analytical_sql_is_allowed(sql):
    """CTEs, joins, window functions and comments must all pass. Blocking them
    would handicap the arm this experiment measures against."""
    assert _surface().run_sql(sql)["rows"] is not None


# ------------------------------------------------------- it must stay read-only


@pytest.mark.parametrize("sql", [
    "INSERT INTO V_BOOKINGS VALUES (1)",
    "UPDATE V_BOOKINGS SET AMOUNT = 0",
    "DELETE FROM V_BOOKINGS",
    "MERGE INTO V_BOOKINGS USING x ON 1=1 WHEN MATCHED THEN DELETE",
    "CREATE TABLE EVIL (X INT)",
    "DROP TABLE V_BOOKINGS",
    "ALTER TABLE V_BOOKINGS ADD COLUMN X INT",
    "GRANT SELECT ON V_BOOKINGS TO ROLE PUBLIC",
    "TRUNCATE TABLE V_BOOKINGS",
    "COPY INTO @stage FROM V_BOOKINGS",
    "CALL SOME_PROCEDURE()",
    "USE ROLE GAA_FINANCE_GLOBAL",
    "USE SCHEMA GAA.MARTS",
    "EXECUTE IMMEDIATE 'DROP TABLE V_BOOKINGS'",
])
def test_anything_that_is_not_a_read_is_refused(sql):
    with pytest.raises(ToolError):
        _surface().run_sql(sql)


def test_a_second_statement_is_refused():
    """Multi-statement input is how a read becomes a write."""
    with pytest.raises(ToolError, match="single statement"):
        _surface().run_sql("SELECT 1; DROP TABLE V_BOOKINGS")


def test_a_write_hidden_behind_a_comment_is_refused():
    """Comment-stripping happens before the keyword check, so commenting out the
    SELECT does not promote the DELETE to leading position unnoticed."""
    with pytest.raises(ToolError):
        _surface().run_sql("-- SELECT 1\nDELETE FROM V_BOOKINGS")


def test_the_guard_is_an_allow_list_not_a_deny_list():
    """A deny-list of bad words is defeated by the first keyword nobody listed.
    Only SELECT and WITH may lead."""
    from gtm_analyst.mcp.tools import _READ_ONLY_LEADERS

    assert _READ_ONLY_LEADERS == frozenset({"SELECT", "WITH"})


# -------------------------------------------------------------------- auditing


@live
def test_a_refused_statement_is_still_audited(tmp_path):
    """An attempt is more interesting than a success."""
    audit = tmp_path / "audit.jsonl"
    surface = _surface(audit_path=audit)
    with pytest.raises(ToolError):
        surface.run_sql("DROP TABLE V_BOOKINGS")

    entry = json.loads(audit.read_text().splitlines()[-1])
    assert entry["tool"] == "run_sql"
    assert entry["outcome"] == "refused"
    assert "DROP" in entry["error"] or "read" in entry["error"].lower()


@live
def test_run_sql_still_executes_as_the_persona(tmp_path):
    """The guard is a second layer. The warehouse boundary is the first, and it
    must still hold for free SQL."""
    finance = _surface("FINANCE_GLOBAL").run_sql("SELECT DISTINCT REGION FROM V_BOOKINGS")
    emea = _surface("SALES_DIR_EMEA").run_sql("SELECT DISTINCT REGION FROM V_BOOKINGS")
    assert {r["REGION"] for r in finance["rows"]} == {"AMER", "APAC", "EMEA"}
    assert {r["REGION"] for r in emea["rows"]} == {"EMEA"}


@live
def test_free_sql_cannot_reach_another_personas_schema():
    """Refused by the WAREHOUSE, not by the guard above -- which is the point.
    Free SQL is unconstrained in what it may express and still bounded in what
    it may see."""
    with pytest.raises((ProgrammingError, DatabaseError)):
        _surface("REP_INDIVIDUAL").run_sql("SELECT COUNT(*) FROM GAA.FINANCE.V_BOOKINGS")


@live
def test_run_sql_reports_no_metrics_used():
    """Its answer card must be distinguishable from a contract-backed one."""
    result = _surface().run_sql("SELECT 1 AS X")
    assert result["metrics_used"] == []
    assert result["query_id"]


def test_free_sql_reports_lineage_from_its_own_statement():
    """Free SQL has no contract to read lineage from, but the statement names
    its sources. An answer card without lineage is less auditable, and the
    auditability claim should not have an exemption for one arm."""
    from gtm_analyst.mcp.tools import _tables_in

    assert _tables_in("SELECT * FROM V_BOOKINGS") == ["V_BOOKINGS"]
    assert _tables_in(
        "SELECT * FROM V_BOOKINGS b JOIN V_REVENUE r ON r.BOOKING_ID = b.BOOKING_ID"
    ) == ["V_BOOKINGS", "V_REVENUE"]
    # A CTE alias appears alongside real tables. Overstating what was read is
    # the safe direction for an audit trail; silently omitting is not.
    assert "Q" in _tables_in("WITH q AS (SELECT * FROM V_BOOKINGS) SELECT * FROM q")


@live
def test_a_free_sql_answer_card_is_as_auditable_as_a_contract_one():
    result = _surface().run_sql("SELECT COUNT(*) AS N FROM V_BOOKINGS")
    assert result["lineage"] == ["V_BOOKINGS"]
    assert result["query_id"]
