"""Authentication for the MCP server's network transports.

The server binds a persona when it starts and trusts its transport. Over stdio
that is sound: the pipe comes from a process the user started, and the operating
system is the boundary. The SDK also speaks `sse` and `streamable-http`, where
"trusts its transport" means anyone who can reach the port is the persona.

So the rule is not "add auth", it is: a network transport MUST NOT START without
a credential. A server that warns and starts anyway is a server that is running,
and the warning scrolls off.
"""
import secrets

# Long enough that guessing is not the attack. 32 characters of a generated
# token is ~190 bits of base64; the floor exists to stop "changeme" rather than
# to express a considered entropy target.
MIN_TOKEN_LENGTH = 32

_LOCAL_TRANSPORTS = frozenset({"stdio"})
_NETWORK_TRANSPORTS = frozenset({"sse", "streamable-http"})

_BEARER = "bearer"


class AuthError(RuntimeError):
    """Raised before the server binds a port, never after."""


def require_token_for_transport(transport: str, token: str | None) -> None:
    """Refuse to start a network transport without an adequate token.

    An unknown transport raises rather than falling through to the stdio path.
    New transports arrive in SDK releases without asking, and the safe default
    for something this code has not considered is "no".
    """
    if transport in _LOCAL_TRANSPORTS:
        return
    if transport not in _NETWORK_TRANSPORTS:
        raise AuthError(
            f"unknown transport {transport!r}; refusing to guess whether it is "
            f"reachable from the network"
        )
    if not token:
        raise AuthError(
            f"transport {transport!r} is network-reachable and requires "
            f"GAA_MCP_TOKEN; over the network, the persona this server is bound "
            f"to is whoever can reach the port"
        )
    if len(token) < MIN_TOKEN_LENGTH:
        raise AuthError(
            f"GAA_MCP_TOKEN must be at least {MIN_TOKEN_LENGTH} characters; a "
            f"guessable token is the same exposure plus the belief it is closed"
        )


def token_matches(expected: str, header: str | None) -> bool:
    """Constant-time check of an `Authorization: Bearer <token>` header.

    compare_digest rather than `==` so the token cannot be recovered one
    character at a time from response timing. The scheme is matched
    case-insensitively per RFC 7235 -- rejecting `bearer` would be a
    compatibility bug wearing a security costume.
    """
    if not header:
        return False
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != _BEARER or not presented:
        return False
    return secrets.compare_digest(presented, expected)
