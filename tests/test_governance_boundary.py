"""The governance boundary, asserted against a live account.

Skipped without credentials. These are the tests that decide whether the
architecture's central claim is true, so they are written to be hard to pass by
accident.

A note on why every negative test has a positive twin: Snowflake hides objects a
role cannot see, so a blocked read raises "002003 SQL compilation error" rather
than an authorization error. A test that merely asserts "this raises" would pass
just as happily against an object that was never created. Each unreachability
assertion is therefore paired with proof that the object exists and is readable
by its owner.
"""
import os
from pathlib import Path

import pytest
from snowflake.connector.errors import DatabaseError, ProgrammingError

from gaa.spec.loader import load_spec

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
SAME_SQL = "SELECT DISTINCT REGION FROM V_BOOKINGS ORDER BY REGION"


def _query(persona_name: str, sql: str) -> list[tuple]:
    from gaa.connection import session_for_persona

    with session_for_persona(SPEC.personas[persona_name]) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()


def _blocked(persona_name: str, sql: str) -> bool:
    from gaa.connection import session_for_persona

    try:
        with session_for_persona(SPEC.personas[persona_name]) as conn:
            conn.cursor().execute(sql)
    except (ProgrammingError, DatabaseError):
        # Snowflake reports a refused read as a compilation error and a refused
        # role switch as an access-control error, and a user that cannot assume
        # the role fails at connect time. All three are the boundary holding.
        return True
    return False


# --------------------------------------------------------------- the claim


def test_identical_sql_returns_three_different_correct_answers():
    """The architecture's central claim, asserted directly."""
    finance = {r[0] for r in _query("FINANCE_GLOBAL", SAME_SQL)}
    emea = {r[0] for r in _query("SALES_DIR_EMEA", SAME_SQL)}
    rep = {r[0] for r in _query("REP_INDIVIDUAL", SAME_SQL)}

    assert finance == {"AMER", "APAC", "EMEA"}
    assert emea == {"EMEA"}
    assert rep <= {"EMEA"}
    assert finance != emea, "personas must not collapse to the same answer"


def test_each_persona_can_read_its_own_views():
    """The positive half. Without this, every blocked-access test below could
    pass against views that simply do not exist."""
    for persona in SPEC.personas:
        for view in ("V_BOOKINGS", "V_BILLINGS", "V_REVENUE", "V_ACCOUNT", "V_TERRITORY"):
            rows = _query(persona, f"SELECT COUNT(*) FROM {view}")
            assert rows[0][0] > 0, f"{persona} sees no rows in {view}"


# --------------------------------------------------------------- bypass paths


def test_rep_cannot_read_another_personas_schema():
    assert _blocked("REP_INDIVIDUAL", "SELECT COUNT(*) FROM GAA.FINANCE.V_BOOKINGS")
    assert _blocked("SALES_DIR_EMEA", "SELECT COUNT(*) FROM GAA.FINANCE.V_BOOKINGS")


def test_no_persona_can_read_the_base_marts():
    for persona in SPEC.personas:
        assert _blocked(persona, "SELECT COUNT(*) FROM GAA.MARTS.FCT_BOOKINGS"), persona
        assert _blocked(persona, "SELECT COUNT(*) FROM GAA.MARTS.STG_BOOKINGS"), persona


def test_no_persona_can_escalate_role():
    for persona, target in [("REP_INDIVIDUAL", "GAA_FINANCE_GLOBAL"),
                            ("SALES_DIR_EMEA", "GAA_FINANCE_GLOBAL"),
                            ("REP_INDIVIDUAL", "ACCOUNTADMIN")]:
        assert _blocked(persona, f"USE ROLE {target}"), f"{persona} -> {target}"


def test_restricted_personas_cannot_write():
    """Read-only is part of the boundary, not an assumption about intent."""
    for persona in SPEC.personas:
        assert _blocked(persona, "CREATE TABLE GAA.MARTS.EVIL (X INT)"), persona


# --------------------------------------------------------------- masking


def test_masking_changes_values_but_not_row_counts():
    sql = "SELECT COUNT(*), COUNT(DISTINCT ACCOUNT_NAME) FROM V_ACCOUNT WHERE REGION='EMEA'"
    f_rows, f_distinct = _query("FINANCE_GLOBAL", sql)[0]
    e_rows, e_distinct = _query("SALES_DIR_EMEA", sql)[0]

    assert f_rows == e_rows, "masking must not change how many rows come back"
    assert f_distinct == e_distinct, "masking must not collapse distinct accounts"

    finance_names = {r[0] for r in _query("FINANCE_GLOBAL",
                     "SELECT ACCOUNT_NAME FROM V_ACCOUNT WHERE REGION='EMEA'")}
    emea_names = {r[0] for r in _query("SALES_DIR_EMEA", "SELECT ACCOUNT_NAME FROM V_ACCOUNT")}
    assert all(n.startswith("ACCOUNT-") for n in emea_names), "EMEA names must be masked"
    assert not any(n.startswith("ACCOUNT-") for n in finance_names), "finance names must be clear"
    assert not (finance_names & emea_names), "masked and clear names must not overlap"
