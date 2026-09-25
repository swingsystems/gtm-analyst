"""The tool surface is the governance boundary.

Integration tests; skipped without credentials. The structural point these
assert: a persona is bound when the surface is CONSTRUCTED, never passed as a
tool argument. If an agent could name its own role, the boundary would live in
the prompt rather than in the warehouse.
"""
import inspect
import json
import os
from pathlib import Path

import pytest

from gtm_analyst.mcp.tools import ToolError, ToolSurface
from gtm_analyst.spec.loader import load_spec

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
CONTRACTS = Path(__file__).parent.parent / "semantic" / "contracts"

live = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)


def _surface(persona_name, audit_path=None):
    return ToolSurface(SPEC.personas[persona_name], CONTRACTS, audit_path=audit_path)


# ------------------------------------------------------------------ structure


def test_no_tool_accepts_a_persona_role_or_schema_argument():
    """The structural guarantee. A tool that took a role would let the caller
    choose its own privileges, and no amount of prompt discipline would fix it."""
    forbidden = {"persona", "role", "schema", "user", "snowflake_role"}
    for name in ToolSurface.TOOLS:
        params = set(inspect.signature(getattr(ToolSurface, name)).parameters) - {"self"}
        assert not (params & forbidden), f"{name} accepts {params & forbidden}"


def test_the_surface_exposes_exactly_the_declared_tools():
    """Pinned deliberately. Widening the agent's reach should be an explicit
    edit here, not a side effect of adding a method."""
    assert set(ToolSurface.TOOLS) == {
        "list_metrics", "describe_metric", "query_metric", "run_sql", "explain_lineage",
    }


def test_run_sql_is_available_to_the_free_arm_only_by_convention():
    """Nothing in the surface prevents a contract-constrained agent from calling
    run_sql -- the arms are separated by which tools their prompts describe, not
    by capability. Recorded here because it is a real limitation: a constrained
    agent that decided to write raw SQL would not be stopped by this layer, and
    the experiment depends on it not doing so.

    The warehouse boundary still holds either way, so the risk is to the
    experiment's validity, not to the data.
    """
    assert "run_sql" in ToolSurface.TOOLS


# ------------------------------------------------------------------ discovery


def test_list_metrics_returns_every_contract_the_arm_may_see():
    """Defaults to showing joined metrics. The strict arm constructs its surface
    with allow_joins=False, and that filtering is what separates the two
    constrained arms -- see tests/test_safe_joins.py."""
    metrics = _surface("FINANCE_GLOBAL").list_metrics()
    assert {m["name"] for m in metrics} == {
        "bookings_amount@1", "revenue_amount@1", "billings_amount@1",
        "booking_count@1", "account_count@1", "bookings_by_territory@1",
    }
    assert all(m["description"] for m in metrics)


def test_describe_metric_reports_grain_and_dimensions():
    described = _surface("FINANCE_GLOBAL").describe_metric("revenue_amount@1")
    assert described["grain"]
    assert "segment" in {d["name"] for d in described["dimensions"]}


def test_describe_metric_refuses_an_unknown_name():
    with pytest.raises(ToolError, match="nonexistent"):
        _surface("FINANCE_GLOBAL").describe_metric("nonexistent@1")


# ------------------------------------------------------------------ execution


@live
def test_query_metric_returns_rows_sql_and_a_real_query_id():
    result = _surface("FINANCE_GLOBAL").query_metric(
        "bookings_amount@1", dimensions=["region"], period="2026-Q3")
    assert result["rows"]
    assert "SUM(AMOUNT)" in result["sql"]
    assert result["metrics_used"] == ["bookings_amount@1"]
    assert result["query_id"]
    assert result["context"]["role"] == "GAA_FINANCE_GLOBAL"


@live
def test_the_same_request_returns_different_rows_per_persona():
    """The whole architecture in one assertion."""
    def regions(persona):
        result = _surface(persona).query_metric(
            "bookings_amount@1", dimensions=["region"], period="2026-Q3")
        return {r["REGION"] for r in result["rows"]}

    assert regions("FINANCE_GLOBAL") == {"AMER", "APAC", "EMEA"}
    assert regions("SALES_DIR_EMEA") == {"EMEA"}


@live
def test_values_come_back_as_strings_not_floats():
    """Compared as floats, a rounding artifact is indistinguishable from a real
    discrepancy -- the class of error this whole evaluation exists to detect."""
    result = _surface("FINANCE_GLOBAL").query_metric(
        "bookings_amount@1", dimensions=["region"], period="2026-Q3")
    for row in result["rows"]:
        assert isinstance(row["VALUE"], str)
        assert "." in row["VALUE"]


@live
def test_an_undeclared_dimension_is_refused_before_touching_snowflake():
    with pytest.raises(ToolError, match="owner_rep"):
        _surface("FINANCE_GLOBAL").query_metric(
            "bookings_amount@1", dimensions=["owner_rep"], period="2026-Q3")


# ------------------------------------------------------------------ audit


@live
def test_every_call_is_audited_with_its_persona_and_query_id(tmp_path):
    audit = tmp_path / "audit.jsonl"
    surface = _surface("SALES_DIR_EMEA", audit_path=audit)
    surface.query_metric("revenue_amount@1", dimensions=["segment"], period="2026-Q3")

    lines = [json.loads(line) for line in audit.read_text().splitlines()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["persona"] == "SALES_DIR_EMEA"
    assert entry["role"] == "GAA_SALES_DIR_EMEA"
    assert entry["tool"] == "query_metric"
    assert entry["metrics_used"] == ["revenue_amount@1"]
    assert entry["query_id"]
    assert entry["duration_ms"] >= 0


@live
def test_a_refused_call_is_still_audited(tmp_path):
    """An attempt is more interesting than a success. A boundary that only logs
    what it allowed cannot tell you what it stopped."""
    audit = tmp_path / "audit.jsonl"
    surface = _surface("REP_INDIVIDUAL", audit_path=audit)
    with pytest.raises(ToolError):
        surface.query_metric("bookings_amount@1", dimensions=["nope"], period="2026-Q3")

    entries = [json.loads(line) for line in audit.read_text().splitlines()]
    assert entries and entries[-1]["outcome"] == "refused"
    assert entries[-1]["error"]
