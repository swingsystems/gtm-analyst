"""Snowflake sessions bound to a single persona.

The persona's role and schema are both fixed at connect time and never changed
afterwards. The schema is as load-bearing as the role: reference SQL is
unqualified, so the session's default schema is what makes identical SQL resolve
to that persona's view. See docs/adr/0001-governance-on-standard-edition.md.
"""
from collections.abc import Iterator
from contextlib import contextmanager

import snowflake.connector

# Bind values server-side rather than interpolating them into the statement
# client-side. See gaa/semantic/compile.py for why this matters here.
snowflake.connector.paramstyle = "qmark"
from cryptography.hazmat.primitives import serialization

from gaa.config import Settings, load_settings
from gaa.spec.models import Persona


def private_key_der(settings: Settings) -> bytes:
    """Load the key-pair private key and return it in the DER form the connector wants."""
    passphrase = settings.snowflake_private_key_passphrase
    with settings.snowflake_private_key_path.open("rb") as fh:
        key = serialization.load_pem_private_key(
            fh.read(), password=passphrase.encode() if passphrase else None
        )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def user_for_persona(persona: Persona, settings: Settings) -> str:
    """The Snowflake user a persona connects as.

    Each persona gets its own service user holding exactly ONE role. Without
    that, the boundary is not real: a session opened as GAA_REP_INDIVIDUAL can
    run USE ROLE GAA_FINANCE_GLOBAL and read everything, because Snowflake scopes
    privilege to the session role but lets a session switch to any role its USER
    holds. The schema grants were never the weak point; the user's role portfolio
    was.

    The mapping is by convention rather than configuration because the persona
    spec is frozen, and because a Snowflake user account is a deployment detail
    that has no business appearing in an evaluation spec.
    """
    prefix = settings.snowflake_service_user_prefix
    if prefix and persona.service_user:
        return f"{prefix}{persona.name}"
    return settings.snowflake_user


@contextmanager
def session_for_persona(
    persona: Persona, settings: Settings | None = None
) -> Iterator[snowflake.connector.SnowflakeConnection]:
    """Open a Snowflake session as one persona. No code path elevates it afterwards."""
    settings = settings or load_settings()
    conn = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=user_for_persona(persona, settings),
        private_key=private_key_der(settings),
        role=persona.snowflake_role,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=persona.snowflake_schema,
        session_parameters={"QUERY_TAG": f"gaa:{persona.name}"},
    )
    try:
        yield conn
    finally:
        conn.close()
