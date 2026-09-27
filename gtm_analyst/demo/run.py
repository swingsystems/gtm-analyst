"""Tier 0: the whole pipeline, no account, no key, about five minutes.

Adoption dies at this gate, so the constraint is hard: no network, no
credentials, no setup. What it shows is genuine — recorded answer cards from
live runs against a real warehouse, each carrying the Snowflake query id of the
statement that produced it.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from gtm_analyst.agent.card import AnswerCard, strip_sidecars
from gtm_analyst.harness.score import _numeric_total


class DemoError(Exception):
    """Raised when the demo cannot show what it promises."""


@dataclass
class DemoResult:
    answer_card: AnswerCard | None = None
    refusal_card: AnswerCard | None = None
    persona_comparison: dict[str, AnswerCard] = field(default_factory=dict)
    total_cards: int = 0


def _load(cards_path: Path) -> list[tuple[str, AnswerCard]]:
    if not Path(cards_path).exists():
        raise DemoError(
            f"no recorded cards at {cards_path}. The demo replays observed runs and "
            "will not invent them; record with `gtm experiment` or `gtm record-runs`."
        )
    payload = json.loads(Path(cards_path).read_text())
    loaded = []
    for item in payload:
        item = dict(item)
        question_id = item.get("_question_id", "?")
        item = strip_sidecars(item)
        loaded.append((question_id, AnswerCard(**item)))
    if not loaded:
        raise DemoError(f"no recorded cards in {cards_path}")
    return loaded


def run_demo(cards_path: Path, out: Path) -> DemoResult:
    """Render the three things worth seeing, into `out`."""
    cards = _load(cards_path)
    result = DemoResult(total_cards=len(cards))

    for _, card in cards:
        if result.answer_card is None and card.rows and card.sql:
            result.answer_card = card
        if result.refusal_card is None and card.why_not and len(card.why_not) > 30:
            result.refusal_card = card

    # One question, every persona, one arm: the architecture in a single screen.
    by_question: dict[tuple[str, str], dict[str, AnswerCard]] = {}
    for question_id, card in cards:
        by_question.setdefault((question_id, card.arm), {})[card.persona] = card
    for personas in by_question.values():
        if len(personas) >= 2 and len({len(c.rows) for c in personas.values()}) > 1:
            result.persona_comparison = personas
            break
    if not result.persona_comparison:
        for personas in by_question.values():
            if len(personas) >= 2:
                result.persona_comparison = personas
                break

    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(_render(result))
    return result


def _render(result: DemoResult) -> str:
    lines = [
        "# Governed analytics agents — recorded demo",
        "",
        (f"Replaying {result.total_cards} answer cards recorded against a live "
         "Snowflake account. No credentials were used to produce this page, and none "
         "are needed to reproduce it."),
        "",
        "## One question, three identities, three correct answers",
        "",
    ]
    if result.persona_comparison:
        first = next(iter(result.persona_comparison.values()))
        lines += [f"> {first.question}", ""]
        lines += ["| asked as | rows | total | withheld |", "|---|---|---|---|"]
        for persona, card in sorted(result.persona_comparison.items()):
            # Reuse the scorer's extraction rather than reimplementing it. The
            # first version here matched anything digit-shaped and summed an
            # account id into a money column, which is the third time a
            # hand-rolled numeric heuristic has been wrong in this project.
            total = _numeric_total(card.rows)
            withheld = "yes" if card.why_not else "—"
            lines.append(f"| `{persona}` | {len(card.rows)} | {total:,.2f} | {withheld} |")
        lines += ["", ("Same question. Same SQL shape. Different answers, because the "
                       "warehouse — not the prompt — decides what each identity may "
                       "see."), ""]

    if result.answer_card:
        lines += ["## An answer, with everything needed to check it", "",
                  result.answer_card.to_markdown(), ""]

    if result.refusal_card:
        lines += ["## Withholding, stated rather than hidden", "",
                  f"> {result.refusal_card.why_not}", "",
                  ("A smaller number presented as complete is the dangerous failure. "
                   "This is the alternative."), ""]

    lines += ["## What this does not show", "",
              ("Synthetic data. A partial experiment: 25 of 36 cells, stopped by an API "
               "spending limit. One run per cell, and the same question asked repeatedly "
               "has produced row counts of 3, 68, 13 and 68. See `results/` for the "
               "numbers and their limits, and `README.md` for why the evaluation might "
               "still be lying to you."), ""]
    return "\n".join(lines)
