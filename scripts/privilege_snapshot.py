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

from gtm_analyst.config import load_settings
from gtm_analyst.connection import session_for_persona
from gtm_analyst.spec.models import Persona

# The operator is whoever SNOWFLAKE_USER names. Recorded under a stable key so
# the committed baseline carries no username.
OPERATOR_KEY = "user:<operator>"

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


def _holder(row: dict[str, str], operator: str) -> str:
    """One "TYPE:NAME" holder of a role, with the operator normalised.

    The baseline is committed to a public repository and must name no real
    account, and a baseline naming one account's operator cannot be compared
    against anybody else's.
    """
    kind = row.get("granted_to", "")
    name = str(row.get("grantee_name", ""))
    if name.upper() == operator.upper():
        name = "<operator>"
    return f"{kind}:{name}"


def _diff(baseline: dict, live: dict) -> tuple[list[str], list[str]]:
    """What the account has that the baseline does not, and vice versa.

    Both directions matter and they mean different things. An ADDED grant is
    the escalation case -- somebody widened access. A REMOVED grant is the
    breakage case, and it is the one that gets ignored until an agent starts
    refusing questions it answered last week.
    """
    added, removed = [], []
    for principal in sorted(set(baseline) | set(live)):
        was = {json.dumps(g) for g in baseline.get(principal, [])}
        now = {json.dumps(g) for g in live.get(principal, [])}
        added += [f"+ {principal}  {g}" for g in sorted(now - was)]
        removed += [f"- {principal}  {g}" for g in sorted(was - now)]
    return added, removed


@click.command()
@click.option("--out", type=click.Path(path_type=Path),
              help="write the live snapshot here")
@click.option("--baseline", type=click.Path(path_type=Path),
              help="compare the live account against this committed snapshot "
                   "and exit non-zero on any difference")
def main(out: Path | None, baseline: Path | None) -> None:
    settings = load_settings()
    prefix = settings.snowflake_service_user_prefix or "GAA_SVC_"
    snapshot: dict[str, object] = {}

    with session_for_persona(ADMIN, settings) as conn:
        cursor = conn.cursor()
        for role in ROLES:
            snapshot[f"role:{role}"] = _grants(cursor, f"SHOW GRANTS TO ROLE {role}")
            # WHO HOLDS the role, not only what it can do.
            #
            # Without this the detector has a blind spot exactly where it
            # matters: it inspected a fixed list of principals, so creating a
            # NEW user and granting it a persona role was invisible. That is the
            # escalation scenario, not a hypothetical -- provisioning a CI user
            # walked straight through it and the check still said "no drift".
            snapshot[f"holders:{role}"] = sorted(
                _holder(row, settings.snowflake_user)
                for row in _rows(cursor, f"SHOW GRANTS OF ROLE {role}")
            )
        for persona in PERSONAS:
            user = f"{prefix}{persona}"
            # Role portfolio per user. This is the field that made escalation
            # possible: the boundary holds only while each service user holds
            # exactly one role.
            snapshot[f"user:{user}"] = sorted(
                str(row.get("role", "")) for row in
                _rows(cursor, f"SHOW GRANTS TO USER {user}")
            )
        # Keyed by a placeholder, not the operator's actual username. Two
        # reasons, and both matter: the baseline is committed to a public
        # repository, and a baseline naming one account's operator cannot be
        # compared against anybody else's. Drift detection is unaffected
        # because both sides normalise identically.
        snapshot[OPERATOR_KEY] = sorted(
            str(row.get("role", "")) for row in
            _rows(cursor, f"SHOW GRANTS TO USER {settings.snowflake_user}")
        )

    total = sum(len(v) for v in snapshot.values())  # type: ignore[arg-type]

    # A snapshot of nothing would make both convergence and drift trivially pass.
    if total == 0:
        click.echo("refusing to use an empty snapshot; is governance applied?", err=True)
        sys.exit(1)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        click.echo(f"{total} grants across {len(snapshot)} principals -> {out}", err=True)

    if baseline:
        if not baseline.exists():
            click.echo(f"no baseline at {baseline}; write one with --out first", err=True)
            sys.exit(1)
        added, removed = _diff(json.loads(baseline.read_text()), snapshot)
        if not added and not removed:
            click.echo(f"no drift: {total} grants match {baseline}")
            return
        click.echo("PRIVILEGE DRIFT", err=True)
        for line in added + removed:
            click.echo(f"  {line}", err=True)
        click.echo(
            "\nA persona role granted to a human user re-opens role escalation. "
            "Review, then either revert the grant or re-baseline deliberately.",
            err=True,
        )
        sys.exit(1)

    if not out and not baseline:
        click.echo("nothing to do: pass --out, --baseline, or both", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
