"""Dump the account's GAA privilege set as deterministic JSON.

This exists because grants are additive and that has already cost this project
once: narrowing `GRANT ALL ON SCHEMA` to an explicit list changed the SQL but
not the account, and the loader kept ~70 privileges including CREATE SECRET
while the file claimed it held ten.

Reading the DDL tells you what was requested. Only the account tells you what is
true. A deployment that does not converge -- one whose second run leaves a
different privilege set than its first -- is a different system on every run,
and no amount of reviewing the SQL will reveal it.

    uv run python scripts/privilege_snapshot.py --out before.json
    make governance
    uv run python scripts/privilege_snapshot.py --out after.json
    diff before.json after.json

`make verify-convergence` does exactly that and fails on any difference.
"""
import json
import sys
from pathlib import Path

import click

from gaa.config import load_settings
from gaa.connection import session_for_persona
from gaa.spec.models import Persona

ROLES = ("GAA_LOADER", "GAA_FINANCE_GLOBAL", "GAA_SALES_DIR_EMEA", "GAA_REP_INDIVIDUAL")
PERSONAS = ("FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL")

# SHOW GRANTS columns that differ between two identical deployments. created_on
# is a timestamp; grant_option and granted_by are stable but noisy to diff.
# Dropping created_on is the whole reason this is not just `SHOW GRANTS` piped
# to a file.
_GRANT_FIELDS = ("privilege", "granted_on", "name", "granted_to", "grantee_name")

ADMIN = Persona(
    name="ADMIN",
    snowflake_role="ACCOUNTADMIN",
    snowflake_schema="MARTS",
    description="read-only privilege inspection",
    service_user=False,
)


def _rows(cursor, statement: str) -> list[dict[str, str]]:
    cursor.execute(statement)
    columns = [d[0].lower() for d in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _grants(cursor, statement: str) -> list[list[str]]:
    """Normalised, sorted grant tuples. Sorting makes the diff meaningful --
    Snowflake does not promise SHOW GRANTS ordering between calls."""
    out = []
    for row in _rows(cursor, statement):
        out.append([str(row.get(field, "")) for field in _GRANT_FIELDS])
    return sorted(out)


@click.command()
@click.option("--out", type=click.Path(path_type=Path), required=True)
def main(out: Path) -> None:
    settings = load_settings()
    prefix = settings.snowflake_service_user_prefix or "GAA_SVC_"
    snapshot: dict[str, object] = {}

    with session_for_persona(ADMIN, settings) as conn:
        cursor = conn.cursor()
        for role in ROLES:
            snapshot[f"role:{role}"] = _grants(cursor, f"SHOW GRANTS TO ROLE {role}")
        for persona in PERSONAS:
            user = f"{prefix}{persona}"
            # Role portfolio per user. This is the field that made escalation
            # possible: the boundary holds only while each service user holds
            # exactly one role.
            snapshot[f"user:{user}"] = sorted(
                str(row.get("role", "")) for row in
                _rows(cursor, f"SHOW GRANTS TO USER {user}")
            )
        snapshot[f"user:{settings.snowflake_user}"] = sorted(
            str(row.get("role", "")) for row in
            _rows(cursor, f"SHOW GRANTS TO USER {settings.snowflake_user}")
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    total = sum(len(v) for v in snapshot.values())  # type: ignore[arg-type]
    click.echo(f"{total} grants across {len(snapshot)} principals -> {out}", err=True)

    # A snapshot of nothing would make convergence trivially pass.
    if total == 0:
        click.echo("refusing to write an empty snapshot; is governance applied?", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
