import csv
import json
import sys
from pathlib import Path

import click

from gaa.spec.loader import SpecError, load_spec

DEFAULT_SPEC_ROOT = Path("evals/spec")


@click.group()
def cli() -> None:
    """Governed analytics agent tooling."""


@cli.command("spec-validate")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
def spec_validate(root: Path) -> None:
    """Validate the evaluation spec: structure, references, and persona coverage."""
    try:
        spec = load_spec(root)
    except SpecError as exc:
        click.echo(f"spec error: {exc}", err=True)
        sys.exit(1)

    click.echo(
        f"spec ok: {len(spec.questions)} questions, "
        f"{len(spec.personas)} personas, {len(spec.invariants)} invariants"
    )


@cli.command("synth")
@click.option("--profile", type=click.Path(path_type=Path),
              default=Path("warehouse/seeds/profile.yaml"))
@click.option("--out", type=click.Path(path_type=Path), default=Path("warehouse/seeds"))
def synth(profile: Path, out: Path) -> None:
    """Generate synthetic seed data from a profile. Deterministic for a given seed."""
    from gaa.synth.generate import generate
    from gaa.synth.profile import ProfileError, load_profile

    try:
        spec = load_profile(profile)
    except ProfileError as exc:
        click.echo(f"profile error: {exc}", err=True)
        sys.exit(1)

    data = generate(spec, seed=spec.seed)
    for table, rows in sorted(data.items()):
        if table.startswith("_"):
            continue
        path = out / f"{table}.csv"
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"{path}: {len(rows)} rows")
    (out / "_anomalies.json").write_text(json.dumps(data["_anomalies"], indent=2, sort_keys=True))
    click.echo(f"{out / '_anomalies.json'}: anomaly manifest")
