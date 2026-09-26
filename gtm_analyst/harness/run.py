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

from gtm_analyst.agent.card import AnswerCard
from gtm_analyst.agent.runner import ARM_TOOLS, DEFAULT_MODELS, answer
from gtm_analyst.harness.score import Outcome, RefusalKind, Score, score_answer
from gtm_analyst.spec.loader import Spec, load_spec

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
    cards_path: Path | None = None,
    resume_from: Path | None = None,
    provider: str = "anthropic",
    model: str | None = None,
) -> list[Score]:
    """Every question x persona x arm. A missing cell is an error, not an omission.

    Every answer card is persisted, not just its score. Without that, changing
    the scorer means re-running every agent, and nobody can check the scoring
    without paying to reproduce the runs -- which makes the published numbers
    unverifiable by exactly the readers who should be checking them. Two scorer
    bugs were found here already; both would have needed a full re-run to
    confirm.
    """
    spec: Spec = load_spec(spec_root)
    arms = arms or sorted(ARM_TOOLS)
    questions = [q for q in spec.questions if not question_ids or q.id in question_ids]

    # Resume replays recorded cards for cells already run and calls the model
    # only for the rest. The pilot here died mid-grid on a provider spending
    # limit with 25 of 36 cells recorded, and re-running the 25 would have cost
    # real money to reproduce answers already on disk.
    #
    # Recorded cells are RESCORED rather than trusted: a score is cheap and
    # deterministic, the card is the expensive artifact, and carrying forward an
    # old score would silently mix scorer versions in one report. Three scorer
    # bugs have been found in this project, so a report spanning two scorers is
    # a report nobody can interpret.
    # Resume only ever replays cells produced by the SAME model. Reusing a
    # recorded Claude cell inside an OpenAI grid would make an arm difference
    # indistinguishable from a model difference, which is the one error this
    # experiment cannot survive.
    done: dict[tuple[str, str, str], dict] = {}
    if resume_from and resume_from.exists():
        expected_model = model or DEFAULT_MODELS.get(provider)
        for record in json.loads(resume_from.read_text()):
            recorded = (record.get("spend") or {}).get("model")
            if recorded is not None and recorded != expected_model:
                continue
            key = (record["_question_id"], record["persona"], record["arm"])
            done[key] = record

    scores: list[Score] = []
    cards: list[dict] = []
    for question in questions:
        for persona_name, persona in spec.personas.items():
            truth = next(e.rows for e in question.expected if e.persona == persona_name)
            for arm in arms:
                recorded = done.get((question.id, persona_name, arm))
                if recorded is not None:
                    card = AnswerCard.model_validate(
                        {k: v for k, v in recorded.items() if not k.startswith("_")}
                    )
                else:
                    card = answer(question.text, persona, arm, contracts_root,
                                  audit_path=audit_path,
                                  provider=provider, model=model)
                cards.append({**card.model_dump(), "_question_id": question.id})
                scores.append(score_answer(
                    card, truth, PERMITTED_REGIONS[persona_name], question.id, ALL_REGIONS
                ))
                if cards_path:
                    cards_path.parent.mkdir(parents=True, exist_ok=True)
                    cards_path.write_text(json.dumps(cards, indent=2, default=str) + "\n")
    _LAST_CARDS.clear()
    _LAST_CARDS.extend(cards)
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


# The cards from the most recent run, so the CLI can report cost without
# changing run_experiment's return type and every caller with it.
_LAST_CARDS: list[dict] = []


def spend_report(cards: list[dict]) -> str:
    """What the run cost, per arm and in total.

    A SEPARATE file rather than a section inside summary.md. That report's
    schema was pre-registered in ADR 0003 before any number existed, and the
    discipline is only worth something if it survives a change that looks
    harmless -- including this one.

    Cards recorded before spend was measured carry no usage. They are counted as
    unmeasured rather than as zero, because a run that cost money and was not
    instrumented is not a free run.
    """
    from collections import defaultdict
    from decimal import Decimal

    by_arm: dict[str, list[dict]] = defaultdict(list)
    unmeasured = 0
    for card in cards:
        spend = card.get("spend")
        if not spend:
            unmeasured += 1
            continue
        by_arm[card["arm"]].append(spend)

    lines = ["# What this run cost", ""]
    if not by_arm:
        lines += [f"No usage recorded on any of {len(cards)} cards.", ""]
        return "\n".join(lines)

    lines += ["| arm | cells | API calls | input tok | output tok | USD |",
              "|---|---|---|---|---|---|"]
    total = Decimal("0.00")
    for arm in sorted(by_arm):
        rows = by_arm[arm]
        cost = sum((Decimal(r["cost_usd"]) for r in rows), Decimal("0.00"))
        total += cost
        lines.append(
            f"| {arm} | {len(rows)} | {sum(r['api_calls'] for r in rows)} | "
            f"{sum(r['input_tokens'] for r in rows):,} | "
            f"{sum(r['output_tokens'] for r in rows):,} | {cost} |"
        )
    measured = sum(len(v) for v in by_arm.values())
    per_answer = total / measured if measured else Decimal(0)
    headline = (
        f"**Total: ${total}** across {measured} measured cells "
        f"(${per_answer:.4f} per answer)."
    )
    lines += ["", headline]
    if unmeasured:
        note = (
            f"{unmeasured} card(s) carry no usage and are excluded. They predate "
            "spend measurement -- counted as unmeasured rather than as zero, "
            "because an uninstrumented run is not a free one."
        )
        lines += ["", note]
    return "\n".join(lines) + "\n"


def write_results(scores: list[Score], arms: list[str], out: Path,
                  cards: list[dict] | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw.json").write_text(
        json.dumps([{**asdict(s), "outcome": s.outcome.value,
                     "category": s.category.value if s.category else None,
                     "refusal_kind": s.refusal_kind.value} for s in scores],
                   indent=2, sort_keys=True) + "\n"
    )
    (out / "summary.md").write_text(summarise(scores, arms))
    if cards is not None:
        (out / "spend.md").write_text(spend_report(cards))
