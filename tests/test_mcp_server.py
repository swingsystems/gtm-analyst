"""Lineage and the server entrypoint."""
import inspect
import json
from pathlib import Path

import pytest

from gtm_analyst.mcp.tools import ToolError, ToolSurface
from gtm_analyst.spec.loader import load_spec

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
CONTRACTS = Path(__file__).parent.parent / "semantic" / "contracts"
LINEAGE = Path(__file__).parent.parent / "warehouse" / "governance" / "lineage.json"


def _surface(persona="FINANCE_GLOBAL"):
    return ToolSurface(SPEC.personas[persona], CONTRACTS)


def test_lineage_is_build_time_metadata_not_runtime_introspection():
    """A SECURE view hides its definition from anyone who is not its owner, so
    an agent cannot discover what it reads from -- which is the property that
    stops it introspecting its way around the boundary. Lineage exists because
    apply_governance recorded it."""
    assert LINEAGE.exists(), "lineage manifest missing; run scripts/apply_governance.py"
    manifest = json.loads(LINEAGE.read_text())
    assert manifest["GAA.EMEA.V_BOOKINGS"] == ["GAA.MARTS.FCT_BOOKINGS"]


def test_explain_lineage_resolves_to_the_personas_own_view():
    """Each persona is told about ITS view, not a canonical one. The rep and the
    controller read different objects for the same metric, and lineage that
    hid that would be lying by omission."""
    finance = _surface("FINANCE_GLOBAL").explain_lineage("bookings_amount@1")
    emea = _surface("SALES_DIR_EMEA").explain_lineage("bookings_amount@1")

    assert finance["view"] == "GAA.FINANCE.V_BOOKINGS"
    assert emea["view"] == "GAA.EMEA.V_BOOKINGS"
    assert finance["sources"] == ["GAA.MARTS.FCT_BOOKINGS"]
    assert finance["metric"] == "bookings_amount@1"


def test_explain_lineage_reports_the_metric_version():
    lineage = _surface().explain_lineage("revenue_amount@1")
    assert lineage["metric"] == "revenue_amount@1"
    assert lineage["version"] == 1


def test_explain_lineage_refuses_an_unknown_metric():
    with pytest.raises(ToolError, match="nonexistent"):
        _surface().explain_lineage("nonexistent@1")


def test_the_surface_now_exposes_five_tools():
    assert set(ToolSurface.TOOLS) == {
        "list_metrics", "describe_metric", "query_metric", "run_sql", "explain_lineage",
    }


def test_no_tool_accepts_a_persona_role_or_schema_argument():
    """Re-asserted as the surface grows. The guarantee is only worth anything
    if it holds for the tool added last."""
    forbidden = {"persona", "role", "schema", "user", "snowflake_role"}
    for name in ToolSurface.TOOLS:
        params = set(inspect.signature(getattr(ToolSurface, name)).parameters) - {"self"}
        assert not (params & forbidden), f"{name} accepts {params & forbidden}"


def test_every_tool_has_a_docstring_the_server_can_publish():
    """The MCP server advertises these to an agent. An undocumented tool is one
    the agent will use wrongly."""
    for name in ToolSurface.TOOLS:
        doc = inspect.getdoc(getattr(ToolSurface, name))
        assert doc and len(doc) > 40, f"{name} is not documented well enough to publish"


def test_the_server_binds_a_persona_at_construction():
    """One server per persona. An agent connects to a server already bound to
    one identity, with no protocol-level way to ask for another."""
    from gtm_analyst.mcp.server import build_server

    server = build_server("SALES_DIR_EMEA", CONTRACTS)
    assert "sales_dir_emea" in server.name


def test_the_server_refuses_an_unknown_persona():
    from gtm_analyst.mcp.server import build_server

    with pytest.raises(ValueError, match="unknown persona"):
        build_server("SUPERUSER", CONTRACTS)


@pytest.mark.anyio
async def test_the_server_publishes_every_tool_with_a_description():
    """A tool published without a description is one the agent will use wrongly,
    and a constrained arm handicapped by poor tool docs would underperform for
    reasons that have nothing to do with semantic grounding."""
    from gtm_analyst.mcp.server import build_server

    tools = await build_server("FINANCE_GLOBAL", CONTRACTS).list_tools()
    assert {t.name for t in tools} == set(ToolSurface.TOOLS)
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name


@pytest.mark.anyio
async def test_no_published_tool_accepts_a_role_or_schema_argument():
    """The structural guarantee, carried out to the protocol boundary. Schemas
    are derived from real method signatures, so this cannot drift from what the
    surface actually accepts."""
    from gtm_analyst.mcp.server import build_server

    forbidden = {"persona", "role", "schema", "user", "snowflake_role"}
    tools = await build_server("FINANCE_GLOBAL", CONTRACTS).list_tools()
    for tool in tools:
        properties = set((tool.input_schema or {}).get("properties", {}))
        assert not (properties & forbidden), f"{tool.name} accepts {properties & forbidden}"


@pytest.fixture
def anyio_backend():
    return "asyncio"
