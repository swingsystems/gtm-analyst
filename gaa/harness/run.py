"""Run every question through every arm as every persona, and report it.

The reporting shape is fixed by docs/adr/0003-three-arms-and-pre-registered-reporting.md,
committed before any number existed. A single aggregate accuracy figure is
never emitted: the likeliest route to a result that is technically correct and
substantively misleading is reporting one arm's error rate over only what it
could attempt beside another's over everything, and letting the reader average
them.
"""
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from gaa.agent.runner import ARM_TOOLS, answer
from gaa.harness.score import Outcome, RefusalKind, Score, score_answer
from gaa.spec.loader import Spec, load_spec

PERMITTED_REGIONS = {
    "FINANCE_GLOBAL": {"AMER", "APAC", "EMEA"},
    "SALES_DIR_EMEA": {"EMEA"},
    "REP_INDIVIDUAL": {"EMEA"},
}
ALL_REGIONS = {"AMER", "APAC", "EMEA"}


def run_experiment(
    spec_root: Path,
    contracts_root: Path,
    arms: list[str] | None = None,
    question_ids: list[str] | None = None,
    audit_path: Path | None = None,
) -> list[Score]:
    """Every question x persona x arm. A missing cell is an error, not an omission."""
    spec: Spec = load_spec(spec_root)
    arms = arms or sorted(ARM_TOOLS)
    questions = [q for q in spec.questions if not question_ids or q.id in question_ids]

    scores: list[Score] = []
    for question in questions:
        for persona_name, persona in spec.personas.items():
            truth = next(e.rows for e in question.expected if e.persona == persona_name)
            for arm in arms:
                card = answer(question.text, persona, arm, contracts_root,
                              audit_path=audit_path)
                scores.append(score_answer(
                    card, truth, PERMITTED_REGIONS[persona_name], question.id, ALL_REGIONS
                ))
    return scores


def summarise(scores: list[Score], arms: list[str]) -> str:
    """Render the pre-registered report. Every section is required."""
    by_arm: dict[str, list[Score]] = defaultdict(list)
    for score in scores:
        by_arm[score.arm].append(score)

    lines = ["# Experiment results", ""]
    lines += [
        ("Reported under the schema fixed in "
         "`docs/adr/0003-three-arms-and-pre-registered-reporting.md` before any "
         "number existed. There is deliberately no single accuracy figure."),
        "",
    ]

    lines += ["## Coverage and conditional accuracy", "",
              "| arm | attempted | coverage | correct | conditional accuracy |",
              "|---|---|---|---|---|"]
    for arm in arms:
        rows = by_arm[arm]
        attempted = [s for s in rows if s.outcome is not Outcome.INEXPRESSIBLE]
        correct = [s for s in attempted if s.outcome is Outcome.CORRECT]
        coverage = f"{len(attempted)}/{len(rows)}" if rows else "0/0"
        accuracy = f"{len(correct) / len(attempted):.0%}" if attempted else "n/a"
        lines.append(f"| {arm} | {len(attempted)} | {coverage} | {len(correct)} | {accuracy} |")

    lines += ["", ("**Coverage is not accuracy.** An arm that declines half the questions "
                   "and is right about the rest has higher conditional accuracy and less "
                   "use."), ""]

    lines += ["## Refusals, by kind", "",
              "| arm | appropriate | capability | total |", "|---|---|---|---|"]
    for arm in arms:
        kinds = Counter(s.refusal_kind for s in by_arm[arm])
        appropriate = kinds[RefusalKind.APPROPRIATE]
        capability = kinds[RefusalKind.CAPABILITY]
        lines.append(f"| {arm} | {appropriate} | {capability} | {appropriate + capability} |")
    lines += ["", ("Declining an ambiguous question and being unable to express one are "
                   "different things and are never summed."), ""]

    expressible_everywhere = {
        s.question_id for s in scores
        if all(x.outcome is not Outcome.INEXPRESSIBLE
               for x in scores if x.question_id == s.question_id)
    }
    expressed = ", ".join(sorted(expressible_everywhere)) or "none"
    lines += ["## Head to head", "",
              f"Questions every arm could express: {len(expressible_everywhere)} ({expressed})",
              "", "| arm | correct | of | accuracy |", "|---|---|---|---|"]
    for arm in arms:
        rows = [s for s in by_arm[arm] if s.question_id in expressible_everywhere]
        correct = sum(1 for s in rows if s.outcome is Outcome.CORRECT)
        rate = f"{correct / len(rows):.0%}" if rows else "n/a"
        lines.append(f"| {arm} | {correct} | {len(rows)} | {rate} |")
    lines += ["", "The only like-for-like comparison in this document.", ""]

    strict_gaps = {s.question_id for s in scores
                   if s.arm == "strict-contract" and s.outcome is Outcome.INEXPRESSIBLE}
    gaps = ", ".join(sorted(strict_gaps)) or "none"
    lines += ["## Safety bonus", "",
              f"Questions the strict arm could not express: {gaps}", ""]
    if strict_gaps:
        lines += ["| arm | wrong on those questions | of |", "|---|---|---|"]
        for arm in arms:
            rows = [s for s in by_arm[arm] if s.question_id in strict_gaps]
            wrong = sum(1 for s in rows if s.outcome is Outcome.WRONG)
            lines.append(f"| {arm} | {wrong} | {len(rows)} |")
        lines += ["", ("The strict arm's inexpressibility is only a safety property if "
                       "the other arms actually got these wrong. This is that number, and "
                       "it is conditional."), ""]

    lines += ["## Failure categories", "",
              ("Denominators are questions where the category is testable for that arm, "
               "never the full set."), "",
              "| arm | category | count |", "|---|---|---|"]
    for arm in arms:
        for category, count in sorted(
            Counter(s.category.value for s in by_arm[arm] if s.category).items()
        ):
            lines.append(f"| {arm} | {category} | {count} |")

    lines += ["", "## Every cell", "",
              "| question | persona | arm | outcome | category | note |",
              "|---|---|---|---|---|---|"]
    for score in sorted(scores, key=lambda s: (s.question_id, s.persona, s.arm)):
        flags = ",".join(f for f, v in [
            ("total", score.totals_match), ("shape", score.shape_matches),
            ("superset", score.is_superset), ("declared", score.declared_withholding),
        ] if v)
        lines.append(
            f"| {score.question_id} | {score.persona} | {score.arm} | "
            f"{score.outcome.value} | {score.category.value if score.category else '—'} | "
            f"{flags or '—'} |"
        )
    return "\n".join(lines) + "\n"


def write_results(scores: list[Score], arms: list[str], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw.json").write_text(
        json.dumps([{**asdict(s), "outcome": s.outcome.value,
                     "category": s.category.value if s.category else None,
                     "refusal_kind": s.refusal_kind.value} for s in scores],
                   indent=2, sort_keys=True) + "\n"
    )
    (out / "summary.md").write_text(summarise(scores, arms))
