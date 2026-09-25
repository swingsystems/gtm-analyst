"""Deterministic replay of recorded agent runs.

Tier 0 of the adoption path: someone with no Snowflake account and no API key
can still see real answer cards, real refusals and a real evaluation report. The
cards are recorded from live runs rather than written by hand, which is the only
reason showing them demonstrates anything.

It never fabricates. An unrecorded question raises, because a mock that invents
an answer turns the demo into a claim about behaviour that was never observed.
"""
import json
from pathlib import Path

from gtm_analyst.agent.card import AnswerCard


def _key(question_id: str, persona: str, arm: str) -> str:
    return f"{question_id}__{persona}__{arm}"


def record_run(directory: Path, question_id: str, card: AnswerCard) -> Path:
    """Write one real run to disk for later replay."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_key(question_id, card.persona, card.arm)}.json"
    payload = card.model_dump()
    payload["_question_id"] = question_id
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


class MockAgent:
    """Replays recorded cards. Requires no credentials of any kind."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.recorded: dict[str, AnswerCard] = {}
        for path in sorted(self.directory.glob("*.json")):
            payload = json.loads(path.read_text())
            question_id = payload.pop("_question_id", path.stem.split("__")[0])
            card = AnswerCard(**payload)
            self.recorded[_key(question_id, card.persona, card.arm)] = card

    def answer(self, question_id: str, persona: str, arm: str) -> AnswerCard:
        key = _key(question_id, persona, arm)
        if key not in self.recorded:
            raise KeyError(
                f"no recorded run for {key}. The mock replays observed behaviour and "
                f"will not invent an answer; record it with gtm record-runs."
            )
        return self.recorded[key]
