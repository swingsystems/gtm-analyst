"""Declared joins with compiler-mandatory predicates.

The agent never writes a join, so it cannot forget a predicate. The party who
CAN forget is whoever authors the contract, which is where enforcement belongs:
a join onto an effective-dated table without a validity window is rejected when
the contract loads, not when a number comes out wrong three quarters later.
"""
import pytest
from pydantic import ValidationError

from gtm_analyst.semantic.models import Join, JoinKey, MetricContract, ValidityWindow


def _join(**overrides):
    base = {
        "name": "territory",
        "table": "V_TERRITORY",
        "keys": [JoinKey(left="OWNER_REP_ID", right="REP_ID")],
        "effective_dated": True,
        "validity": ValidityWindow(
            left_date="BOOKING_DATE", valid_from="VALID_FROM", valid_to="VALID_TO"
        ),
        "dimensions": [],
    }
    base.update(overrides)
    return Join(**base)


def test_a_join_with_its_validity_window_builds():
    join = _join()
    assert join.validity.left_date == "BOOKING_DATE"


def test_an_effective_dated_join_without_a_validity_window_is_refused():
    """The whole point. A rep reassigned mid-quarter appears in two rows, and a
    join that ignores the window either multiplies every booking or drops the
    ones at the boundary. Both look like plausible numbers."""
    with pytest.raises(ValidationError, match="validity"):
        _join(validity=None)


def test_a_join_onto_a_static_table_needs_no_window():
    join = _join(name="account", table="V_ACCOUNT", effective_dated=False, validity=None,
                 keys=[JoinKey(left="ACCOUNT_ID", right="ACCOUNT_ID")])
    assert join.validity is None


def test_join_identifiers_are_validated_like_every_other():
    with pytest.raises(ValidationError):
        _join(table="V_TERRITORY; DROP TABLE X")
    with pytest.raises(ValidationError):
        JoinKey(left="A B", right="REP_ID")


def test_the_validity_window_is_half_open_by_declaration():
    """[valid_from, valid_to). The inclusive reading silently drops bookings on
    a handover date, which is how q011's ground truth was wrong for a day."""
    assert ValidityWindow(
        left_date="BOOKING_DATE", valid_from="VALID_FROM", valid_to="VALID_TO"
    ).half_open is True


def test_a_contract_may_declare_no_joins_at_all():
    """The strict arm's contracts are the same model with an empty joins list,
    so the two arms differ in configuration rather than in code."""
    contract = MetricContract(
        name="m", version=1, description="d" * 40, owner="o", table="V_BOOKINGS",
        grain="booking", measure={"column": "AMOUNT", "aggregation": "sum"},
        dimensions=[], default_filters=[], null_policy="preserve",
        period_column="FISCAL_QUARTER",
    )
    assert contract.joins == []


# --------------------------------------------------------------- compilation

from pathlib import Path

from gtm_analyst.semantic.compile import CompileError, QueryRequest, compile_query
from gtm_analyst.semantic.loader import ContractSet


def _joined_contract():
    return MetricContract(
        name="bookings_by_territory", version=1,
        description="Bookings attributed to the territory in force on the booking date.",
        owner="sales-ops", table="V_BOOKINGS", grain="booking",
        measure={"column": "AMOUNT", "aggregation": "sum"},
        dimensions=[{"name": "region", "column": "REGION", "description": "Account region"}],
        joins=[_join(dimensions=[
            {"name": "territory_id", "column": "TERRITORY_ID",
             "description": "Territory in force when the booking was signed"}])],
        default_filters=[], null_policy="exclude", period_column="FISCAL_QUARTER",
    )


def _contracts():
    contract = _joined_contract()
    return ContractSet(metrics={"bookings_by_territory@1": contract}, root=Path("."))


def test_the_compiler_emits_the_validity_predicate_without_being_asked():
    """The agent supplies a dimension name. Everything that makes the join
    correct is added by the compiler, so there is no path by which it is
    omitted."""
    compiled = compile_query(_contracts(), QueryRequest(
        metric="bookings_by_territory@1", dimensions=["territory_id"], period="2026-Q3"))
    sql = compiled.sql.upper()
    assert "JOIN V_TERRITORY" in sql
    assert "OWNER_REP_ID" in sql and "REP_ID" in sql
    assert "BOOKING_DATE >=" in sql and "BOOKING_DATE <" in sql
    assert "VALID_FROM" in sql and "VALID_TO" in sql


def test_the_window_is_half_open_in_the_generated_sql():
    """>= VALID_FROM AND < VALID_TO. The inclusive form drops handover-date rows."""
    sql = compile_query(_contracts(), QueryRequest(
        metric="bookings_by_territory@1", dimensions=["territory_id"],
        period="2026-Q3")).sql.upper()
    assert "< " in sql.split("VALID_TO")[0][-40:] or "<VALID_TO" in sql.replace(" ", "")
    assert "<= VALID_TO" not in sql


def test_a_joined_dimension_is_reachable_and_a_bogus_one_is_not():
    compiled = compile_query(_contracts(), QueryRequest(
        metric="bookings_by_territory@1", dimensions=["region", "territory_id"],
        period="2026-Q3"))
    assert "TERRITORY_ID" in compiled.sql.upper()
    with pytest.raises(CompileError, match="not declared"):
        compile_query(_contracts(), QueryRequest(
            metric="bookings_by_territory@1", dimensions=["salary"], period="2026-Q3"))


def test_lineage_names_the_joined_table_too():
    """An answer card that hid the joined table would understate what was read."""
    compiled = compile_query(_contracts(), QueryRequest(
        metric="bookings_by_territory@1", dimensions=["territory_id"], period="2026-Q3"))
    assert set(compiled.lineage) == {"V_BOOKINGS", "V_TERRITORY"}


def test_values_still_bind_as_parameters_across_a_join():
    attack = "'; DROP TABLE V_BOOKINGS; --"
    compiled = compile_query(_contracts(), QueryRequest(
        metric="bookings_by_territory@1", dimensions=["territory_id"],
        filters=[{"column": "REGION", "op": "eq", "value": attack}], period="2026-Q3"))
    assert attack not in compiled.sql
    assert attack in compiled.params


def test_the_strict_arm_cannot_see_a_joined_metric():
    """The only difference between the two constrained arms, and it has to be
    enforced: both read the same contracts directory, so a join-bearing contract
    added for the safe-join arm is visible to the strict one unless filtered,
    and the experiment quietly compares an arm against itself."""
    from gtm_analyst.mcp.tools import ToolSurface
    from gtm_analyst.spec.loader import load_spec

    spec = load_spec(Path(__file__).parent.parent / "evals" / "spec")
    root = Path(__file__).parent.parent / "semantic" / "contracts"
    persona = spec.personas["FINANCE_GLOBAL"]

    strict = {m["name"] for m in
              ToolSurface(persona, root, allow_joins=False).list_metrics()}
    safe = {m["name"] for m in
            ToolSurface(persona, root, allow_joins=True).list_metrics()}

    assert "bookings_by_territory@1" in safe
    assert "bookings_by_territory@1" not in strict
    assert strict < safe, "the strict arm must see strictly fewer metrics"


def test_the_arm_join_policy_is_declared_for_every_arm():
    from gtm_analyst.agent.runner import ARM_ALLOWS_JOINS, ARM_TOOLS

    assert set(ARM_ALLOWS_JOINS) == set(ARM_TOOLS)
    assert ARM_ALLOWS_JOINS["strict-contract"] is False
