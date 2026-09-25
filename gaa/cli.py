import csv
import json
import sys
from pathlib import Path

import click
import yaml

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


@cli.command("capture-expected")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
@click.option("--dry-run", is_flag=True, help="show results without writing the spec")
def capture_expected(root: Path, dry_run: bool) -> None:
    """Run every question as every persona and write the results into the spec.

    Fills the `expected` blocks ONLY. Question text and reference SQL are frozen
    at the spec commit; this command must never modify them.
    """
    from gaa.runner.reference import run_reference

    spec = load_spec(root)
    for question in spec.questions:
        expected = []
        for persona in spec.personas.values():
            result = run_reference(root, question, persona)
            expected.append({"persona": persona.name, "rows": result.rows})
            click.echo(f"{question.id:6s} {persona.name:<15} {len(result.rows):>3} rows  "
                       f"[{result.query_id}]")
        if dry_run:
            continue
        _write_expected(root / "questions" / f"{question.id}.yaml", expected)
    if dry_run:
        click.echo("\ndry run: spec not written")


def _write_expected(path: Path, expected: list[dict]) -> None:
    """Replace ONLY the expected block, leaving every other byte untouched.

    A full YAML round-trip would rewrite the whole file -- restyling quotes on
    fields that are frozen at the spec commit. The values would be identical and
    the diff would still show them as changed, which undermines the one claim
    this command makes: that it fills expected and nothing else.
    """
    original = path.read_text()
    head, marker, _ = original.partition("\nexpected:")
    if not marker:
        raise ValueError(f"{path}: no expected block to replace")
    block = yaml.safe_dump({"expected": expected}, sort_keys=False, default_flow_style=False)
    path.write_text(f"{head}\n{block}")


@cli.command("check-invariants")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
def check_invariants(root: Path) -> None:
    """Run every question as every persona, then evaluate all invariants."""
    from gaa.runner.invariants import check_invariant
    from gaa.runner.reference import run_reference

    spec = load_spec(root)
    results, repeats = {}, {}
    for question in spec.questions:
        for persona in spec.personas.values():
            key = (question.id, persona.name)
            results[key] = run_reference(root, question, persona)
            repeats[key] = run_reference(root, question, persona)

    failures = 0

    # Determinism is a property of the runs themselves, so it is checked here
    # rather than from a single captured pass.
    drifted = [k for k in results if results[k].rows != repeats[k].rows]
    status = "PASS" if not drifted else "FAIL"
    click.echo(f"[{status}] determinism: {len(results)} question/persona pairs run twice"
               + (f", drifted: {drifted}" if drifted else ""))
    failures += bool(drifted)

    for inv in spec.invariants:
        if inv.kind == "determinism":
            continue
        outcome = check_invariant(inv, results)
        click.echo(f"[{'PASS' if outcome.passed else 'FAIL'}] {outcome.invariant_id}: "
                   f"{outcome.detail}")
        failures += not outcome.passed

    if failures:
        click.echo(f"{failures} invariant(s) failed", err=True)
        sys.exit(1)
    click.echo("all invariants hold")


@cli.command("record-runs")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
@click.option("--out", type=click.Path(path_type=Path), default=Path("fixtures/mock_runs"))
@click.option("--questions", default="", help="comma-separated ids; default a representative set")
@click.option("--contracts", type=click.Path(path_type=Path),
              default=Path("semantic/contracts"))
def record_runs(root: Path, out: Path, questions: str, contracts: Path) -> None:
    """Record real agent runs as fixtures for the no-credentials demo path.

    These are committed and reviewed, so they must be genuine. Anything invented
    here would make the tier-0 demo a claim about behaviour nobody observed.
    """
    from gaa.agent.mock import record_run
    from gaa.agent.runner import ARM_TOOLS, answer

    spec = load_spec(root)
    by_id = {q.id: q for q in spec.questions}
    wanted = [q.strip() for q in questions.split(",") if q.strip()] or [
        "q001", "q003", "q007", "q010", "q011", "q012",
    ]
    for question_id in wanted:
        question = by_id[question_id]
        for persona in spec.personas.values():
            for arm in sorted(ARM_TOOLS):
                card = answer(question.text, persona, arm, contracts)
                path = record_run(out, question_id, card)
                status = "refused" if card.is_refusal else f"{len(card.rows)} rows"
                click.echo(f"{question_id} {persona.name:<15} {arm:<19} {status:<10} {path.name}")
