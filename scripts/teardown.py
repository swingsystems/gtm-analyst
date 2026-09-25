"""Drop everything the reference deployment created.

Separate from apply_governance.py on purpose. Sharing one entry point between
"build it" and "destroy it" means one wrong flag destroys a working deployment,
and the confirmation below is the only thing between a typo and a dropped
database.
"""
import sys
from pathlib import Path

import click

from gtm_analyst.config import load_settings
from gtm_analyst.connection import session_for_persona
from gtm_analyst.spec.sql import sql_statements
from gtm_analyst.spec.template import render
from scripts.apply_governance import ADMIN, _substitutions

TEARDOWN = Path(__file__).parent.parent / "warehouse" / "governance" / "teardown.sql"


@click.command()
@click.option("--yes", is_flag=True, help="skip the confirmation prompt")
def main(yes: bool) -> None:
    settings = load_settings()
    values = _substitutions(settings)
    database = values["database"]

    click.echo(f"This drops DATABASE {database}, the three GAA service users, and", err=True)
    click.echo("the four GAA roles. The warehouse is left alone.", err=True)
    if not yes:
        # click.confirm aborts on EOF, which is the right behaviour in CI: a
        # non-interactive teardown must pass --yes deliberately.
        click.confirm(f"Drop {database} and all GAA roles?", abort=True)

    with session_for_persona(ADMIN, settings) as conn:
        cursor = conn.cursor()
        for statement in sql_statements(render(TEARDOWN.read_text(), values)):
            preview = " ".join(statement.split())[:88]
            try:
                cursor.execute(statement)
                click.echo(f"    ok   {preview}")
            except Exception as exc:  # noqa: BLE001 - report and stop
                click.echo(f"    FAIL {preview}\n         {exc}", err=True)
                sys.exit(1)
    click.echo("torn down")


if __name__ == "__main__":
    main()
