"""MCP server exposing the governed tool surface.

The persona is chosen when the SERVER is started, not per request. An agent
connects to a server already bound to one identity and has no protocol-level way
to ask for another -- the same guarantee ToolSurface makes, carried out to the
wire.

Run one server per persona:

    gaa serve --persona SALES_DIR_EMEA
"""
import inspect
from pathlib import Path

from mcp.server import MCPServer

from gaa.mcp.tools import ToolSurface
from gaa.spec.loader import load_spec

DEFAULT_SPEC_ROOT = Path("evals/spec")


def build_server(
    persona_name: str,
    contracts_root: Path,
    audit_path: Path | None = None,
    spec_root: Path = DEFAULT_SPEC_ROOT,
) -> MCPServer:
    """Build a server bound to one persona for its whole lifetime.

    Tools are registered from the bound surface's methods, so their schemas are
    derived from real signatures rather than from a hand-maintained map that
    could drift away from them.
    """
    spec = load_spec(spec_root)
    if persona_name not in spec.personas:
        raise ValueError(f"unknown persona {persona_name!r}; have {sorted(spec.personas)}")

    surface = ToolSurface(spec.personas[persona_name], contracts_root, audit_path=audit_path)
    server = MCPServer(
        name=f"gaa-{persona_name.lower()}",
        instructions=(
            f"Governed analytics for the {persona_name} persona. Every query runs as "
            f"that identity and returns only what it is permitted to see. Start with "
            f"list_metrics, read describe_metric before relying on a number, and treat "
            f"a refusal as information rather than an error."
        ),
    )

    for name in ToolSurface.TOOLS:
        method = getattr(surface, name)
        server.add_tool(
            method,
            name=name,
            description=inspect.getdoc(getattr(ToolSurface, name)) or "",
        )

    return server


def serve(
    persona_name: str,
    contracts_root: Path,
    audit_path: Path | None = None,
    spec_root: Path = DEFAULT_SPEC_ROOT,
) -> None:
    """Serve over stdio until the client disconnects."""
    build_server(persona_name, contracts_root, audit_path, spec_root).run()
