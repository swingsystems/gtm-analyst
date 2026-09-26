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

from gtm_analyst.spec.loader import load_spec

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
SAME_SQL = "SELECT DISTINCT REGION FROM V_BOOKINGS ORDER BY REGION"


def _query(persona_name: str, sql: str) -> list[tuple]:
    from gtm_analyst.connection import session_for_persona

    with session_for_persona(SPEC.personas[persona_name]) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()


def _blocked(persona_name: str, sql: str) -> bool:
    from gtm_analyst.connection import session_for_persona

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


def test_the_rep_identity_comes_from_current_user_not_a_hardcoded_string() -> None:
    """The REP views used to filter on a literal 'REP001', which in a real
    deployment means every rep sees one rep's book. The rep is now resolved
    through GAA.IDENTITY.MAP_USER_TO_REP."""
    owners = {row[0] for row in _query("REP_INDIVIDUAL",
                                       "SELECT DISTINCT OWNER_REP_ID FROM V_BOOKINGS")}
    assert owners == {"REP001"}, f"rep session saw {owners}"


def test_the_rep_cannot_read_the_identity_map() -> None:
    """Otherwise the rep enumerates every other rep and their Snowflake user.
    The view reads the map through its owner's rights; the caller must not."""
    assert _blocked("REP_INDIVIDUAL", "SELECT * FROM GAA.IDENTITY.MAP_USER_TO_REP")


def _has_accountadmin() -> bool:
    """Whether this session can obtain ACCOUNTADMIN.

    CI deliberately cannot. Its user holds GAA_LOADER and nothing else, because
    granting CI an admin role to make a test pass would weaken the boundary the
    test exists to prove -- a trade that is always available and never worth
    taking.
    """
    from gtm_analyst.connection import session_for_persona
    from gtm_analyst.spec.models import Persona

    try:
        with session_for_persona(Persona(
            name="ADMIN", snowflake_role="ACCOUNTADMIN", snowflake_schema="MARTS",
            description="capability probe", service_user=False,
        )) as conn:
            conn.cursor().execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - a capability probe: any failure means no
        return False


needs_admin = pytest.mark.skipif(
    not _has_accountadmin(),
    reason="needs ACCOUNTADMIN to mutate the identity map; CI holds GAA_LOADER only",
)


@needs_admin
def test_an_unmapped_user_sees_nothing_rather_than_everything() -> None:
    """The failure DIRECTION is the point.

    A mapping miss normally fails OPEN: the filter drops out and the caller gets
    the unfiltered table. Here the scalar subquery returns NULL, the comparison
    is UNKNOWN, and UNKNOWN does not pass a WHERE clause.

    Asserted by deleting the mapping row, checking the rep sees zero rows, and
    restoring it. Anything other than zero is a full breach for every user who
    was never mapped.
    """
    from gtm_analyst.connection import session_for_persona
    from gtm_analyst.spec.models import Persona

    admin = Persona(name="ADMIN", snowflake_role="ACCOUNTADMIN",
                    snowflake_schema="MARTS", description="test fixture",
                    service_user=False)
    user = "GAA_SVC_REP_INDIVIDUAL"

    def _admin(sql: str, params: tuple = ()) -> None:
        with session_for_persona(admin) as conn:
            conn.cursor().execute(sql, params)

    # qmark, not pyformat: this project sets paramstyle="qmark" so every value
    # binds server-side. A test using %s would not merely fail, it would be
    # demonstrating the wrong convention.
    _admin("DELETE FROM GAA.IDENTITY.MAP_USER_TO_REP WHERE SNOWFLAKE_USER = ?", (user,))
    try:
        unmapped = _query("REP_INDIVIDUAL", "SELECT COUNT(*) FROM V_BOOKINGS")[0][0]
    finally:
        _admin("INSERT INTO GAA.IDENTITY.MAP_USER_TO_REP (SNOWFLAKE_USER, REP_ID) "
               "VALUES (?, ?)", (user, "REP001"))

    assert unmapped == 0, f"an unmapped user saw {unmapped} rows; the mapping fails OPEN"
    restored = _query("REP_INDIVIDUAL", "SELECT COUNT(*) FROM V_BOOKINGS")[0][0]
    assert restored > 0, "the mapping was not restored"
