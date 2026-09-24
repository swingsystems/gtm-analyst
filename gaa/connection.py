"""Snowflake sessions bound to a single persona.

The persona's role and schema are both fixed at connect time and never changed
afterwards. The schema is as load-bearing as the role: reference SQL is
unqualified, so the session's default schema is what makes identical SQL resolve
to that persona's view. See docs/adr/0001-governance-on-standard-edition.md.
"""
from collections.abc import Iterator
from contextlib import contextmanager

import snowflake.connector
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


@contextmanager
def session_for_persona(
    persona: Persona, settings: Settings | None = None
) -> Iterator[snowflake.connector.SnowflakeConnection]:
    """Open a Snowflake session as one persona. No code path elevates it afterwards."""
    settings = settings or load_settings()
    conn = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
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
