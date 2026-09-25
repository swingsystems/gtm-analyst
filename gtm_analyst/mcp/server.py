"""MCP server exposing the governed tool surface.

The persona is chosen when the SERVER is started, not per request. An agent
connects to a server already bound to one identity and has no protocol-level way
to ask for another -- the same guarantee ToolSurface makes, carried out to the
wire.

Run one server per persona:

    gtm serve --persona SALES_DIR_EMEA
"""
import inspect
from pathlib import Path

from mcp.server import MCPServer

from gtm_analyst.mcp.auth import require_token_for_transport, token_matches
from gtm_analyst.mcp.tools import ToolSurface
from gtm_analyst.spec.loader import load_spec

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
        name=f"gtm-analyst-{persona_name.lower()}",
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


def bearer_guard(app, expected: str):
    """ASGI wrapper rejecting any request without the right bearer token.

    Wrapping the app rather than registering a route: a route can be bypassed by
    another route, and the whole point is that nothing reaches the tool surface
    unauthenticated. Every HTTP request through this server passes here or does
    not pass.
    """

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if not token_matches(expected, headers.get("authorization")):
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        # RFC 7235 requires this on a 401. Its absence is how a
                        # client learns nothing about why it was refused.
                        (b"www-authenticate", b'Bearer realm="gtm-analyst"'),
                    ],
                })
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await app(scope, receive, send)

    return guarded


def serve(
    persona_name: str,
    contracts_root: Path,
    audit_path: Path | None = None,
    spec_root: Path = DEFAULT_SPEC_ROOT,
    transport: str = "stdio",
    token: str | None = None,
) -> None:
    """Serve until the client disconnects.

    A network transport refuses to start without a token. That check runs BEFORE
    the server is built and before anything binds a port -- refusing after the
    port is open is not refusing.
    """
    require_token_for_transport(transport, token)
    server = build_server(persona_name, contracts_root, audit_path, spec_root)

    if transport == "stdio":
        server.run(transport="stdio")
        return

    import uvicorn

    app = (server.streamable_http_app() if transport == "streamable-http"
           else server.sse_app())
    uvicorn.run(bearer_guard(app, token or ""), host="127.0.0.1", port=8000)
