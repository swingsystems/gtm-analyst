"""The server binds a persona at startup and trusts its transport.

Over stdio that is sound: the transport is a pipe from a process the user
started. The SDK also speaks sse and streamable-http, so network exposure was
one argument away, and on those transports "trusts its transport" means anyone
who can reach the port is the persona.

The gate is not optional and not warned about. A server that starts and prints
a warning is a server that is running.
"""
import pytest

from gtm_analyst.mcp.auth import (
    MIN_TOKEN_LENGTH,
    AuthError,
    require_token_for_transport,
    token_matches,
)


def test_stdio_needs_no_token() -> None:
    """The transport is a pipe from a process the user started. Demanding a
    shared secret there would be ceremony, and ceremony gets disabled."""
    require_token_for_transport("stdio", token=None)


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_a_network_transport_without_a_token_refuses_to_start(transport: str) -> None:
    with pytest.raises(AuthError, match="requires"):
        require_token_for_transport(transport, token=None)


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_a_short_token_is_refused(transport: str) -> None:
    """A token someone can guess is worse than none: it is the same exposure
    plus the belief that it is closed."""
    with pytest.raises(AuthError, match="characters"):
        require_token_for_transport(transport, token="hunter2")


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_an_adequate_token_is_accepted(transport: str) -> None:
    require_token_for_transport(transport, token="x" * MIN_TOKEN_LENGTH)


def test_an_unknown_transport_is_refused_rather_than_assumed_safe() -> None:
    """A transport this code has not considered must not default to the stdio
    path. New SDK transports arrive without asking."""
    with pytest.raises(AuthError, match="unknown transport"):
        require_token_for_transport("carrier-pigeon", token=None)


def test_a_matching_token_passes() -> None:
    assert token_matches("y" * 40, f"Bearer {'y' * 40}")


def test_a_wrong_token_fails() -> None:
    assert not token_matches("y" * 40, f"Bearer {'z' * 40}")


def test_a_missing_or_malformed_header_fails() -> None:
    for header in (None, "", "y" * 40, "Basic abc", "Bearer", "bearer"):
        assert not token_matches("y" * 40, header), header


def test_the_scheme_is_matched_case_insensitively() -> None:
    """RFC 7235 says the scheme is case-insensitive. Rejecting 'bearer' would
    be a compatibility bug that reads as a security feature."""
    assert token_matches("y" * 40, f"bearer {'y' * 40}")


def test_comparison_does_not_short_circuit_on_length() -> None:
    """A prefix must not be accepted, and comparison must be constant-time so
    the token cannot be recovered a character at a time."""
    import inspect

    from gtm_analyst.mcp import auth

    assert not token_matches("y" * 40, f"Bearer {'y' * 39}")
    assert "compare_digest" in inspect.getsource(auth.token_matches)


def test_serve_refuses_a_network_transport_before_binding_anything(monkeypatch) -> None:
    """The check must run before the port opens. Refusing after is not
    refusing, and a bound port with a half-built server is worse than either."""
    import gtm_analyst.mcp.server as server_mod

    built = []
    monkeypatch.setattr(server_mod, "build_server",
                        lambda *a, **k: built.append(1))
    with pytest.raises(AuthError):
        server_mod.serve("FINANCE_GLOBAL", contracts_root=None,
                         transport="streamable-http", token=None)
    assert built == [], "the server was built before the credential was checked"


def test_the_guard_rejects_an_unauthenticated_http_request() -> None:
    import asyncio

    from gtm_analyst.mcp.server import bearer_guard

    reached = []

    async def app(scope, receive, send):
        reached.append(scope)

    sent = []

    async def send(msg):
        sent.append(msg)

    guarded = bearer_guard(app, "t" * 40)
    asyncio.run(guarded({"type": "http", "headers": []}, None, send))

    assert reached == [], "an unauthenticated request reached the tool surface"
    assert sent[0]["status"] == 401
    assert any(k == b"www-authenticate" for k, _ in sent[0]["headers"])


def test_the_guard_admits_a_correctly_authenticated_request() -> None:
    import asyncio

    from gtm_analyst.mcp.server import bearer_guard

    reached = []

    async def app(scope, receive, send):
        reached.append(scope)

    guarded = bearer_guard(app, "t" * 40)
    scope = {"type": "http",
             "headers": [(b"authorization", b"Bearer " + b"t" * 40)]}
    asyncio.run(guarded(scope, None, None))
    assert len(reached) == 1
