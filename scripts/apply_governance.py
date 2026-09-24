"""Apply governance DDL in order, idempotently, with a log of what ran.

Every statement must be re-runnable: CREATE ... IF NOT EXISTS, CREATE OR REPLACE,
or a GRANT. dbt recreates tables and drops dependent views, so this is run after
every build rather than once.

This is the ONLY privileged code path in the repository. Nothing under gaa/ may
use SYSADMIN or SECURITYADMIN, and the bypass suite asserts that separation.
"""
import json
import re
import sys
from pathlib import Path

import click

from gaa.config import load_settings
from gaa.connection import session_for_persona
from gaa.spec.models import Persona
from gaa.spec.sql import sql_statements

GOVERNANCE_DIR = Path(__file__).parent.parent / "warehouse" / "governance"
LINEAGE_PATH = GOVERNANCE_DIR / "lineage.json"

# view name -> source marts, harvested from the CREATE statements themselves.
_VIEW_DEF = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+SECURE\s+VIEW\s+(?P<view>[\w.]+)\s+AS(?P<body>.*?);",
    re.IGNORECASE | re.DOTALL,
)
_SOURCE = re.compile(r"FROM\s+(GAA\.MARTS\.\w+)", re.IGNORECASE)


def _write_lineage() -> dict[str, list[str]]:
    """Record which marts each persona view reads from.

    This has to be built here, at apply time, because it cannot be discovered at
    query time: a SECURE view hides its own definition from anyone who is not
    its owner, which is exactly the property that stops an agent introspecting
    its way around the boundary. The agent gets lineage because we recorded it,
    not because it could look.
    """
    lineage: dict[str, list[str]] = {}
    for path in sorted(GOVERNANCE_DIR.glob("*.sql")):
        for match in _VIEW_DEF.finditer(path.read_text()):
            qualified = match.group("view")
            sources = sorted({s.upper() for s in _SOURCE.findall(match.group("body"))})
            lineage.setdefault(qualified.upper(), [])
            for source in sources:
                if source not in lineage[qualified.upper()]:
                    lineage[qualified.upper()].append(source)
    LINEAGE_PATH.write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n")
    return lineage

# DDL only. The role is elevated on purpose and confined to this script; the
# statements themselves switch to SECURITYADMIN or SYSADMIN as each requires.
ADMIN = Persona(
    name="ADMIN",
    snowflake_role="ACCOUNTADMIN",
    snowflake_schema="MARTS",
    description="governance DDL only",
    service_user=False,
)


@click.command()
@click.option("--only", default=None, help="substring match on filename, e.g. '02_grants'")
def main(only: str | None) -> None:
    settings = load_settings()
    files = sorted(GOVERNANCE_DIR.glob("*.sql"))
    if only:
        files = [f for f in files if only in f.name]
    if not files:
        click.echo("no governance files matched", err=True)
        sys.exit(1)

    with session_for_persona(ADMIN, settings) as conn:
        cursor = conn.cursor()
        for path in files:
            click.echo(f"--- {path.name}")
            for statement in sql_statements(path.read_text()):
                preview = " ".join(statement.split())[:88]
                try:
                    cursor.execute(statement)
                    click.echo(f"    ok   {preview}  [{cursor.sfqid}]")
                except Exception as exc:  # noqa: BLE001 - report and stop on any DDL failure
                    click.echo(f"    FAIL {preview}\n         {exc}", err=True)
                    sys.exit(1)
    lineage = _write_lineage()
    click.echo(f"governance applied; lineage recorded for {len(lineage)} views")


if __name__ == "__main__":
    main()
