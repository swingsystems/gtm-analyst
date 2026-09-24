"""The constrained agent, against the live warehouse and a live model.

Marked slow: these cost tokens and take seconds. They are the only tests that
prove the arm works end to end rather than in parts.
"""
import os
from pathlib import Path

import pytest

from gaa.agent.runner import ARM_TOOLS, answer
from gaa.spec.loader import load_spec

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
CONTRACTS = Path(__file__).parent.parent / "semantic" / "contracts"
QUESTIONS = {q.id: q for q in SPEC.questions}

live = pytest.mark.skipif(
    not (os.environ.get("SNOWFLAKE_ACCOUNT") and os.environ.get("ANTHROPIC_API_KEY")),
    reason="needs Snowflake and Anthropic credentials",
)


def _truth(qid, persona):
    return next(e.rows for e in QUESTIONS[qid].expected if e.persona == persona)


# ------------------------------------------------------------------ structure


def test_the_strict_arm_cannot_see_run_sql():
    """Structural, not advisory. The strict arm is not merely told to avoid raw
    SQL -- run_sql is absent from the tools it is offered, so the separation
    survives an agent that decides to ignore its instructions."""
    assert "run_sql" not in ARM_TOOLS["strict-contract"]
    assert "run_sql" not in ARM_TOOLS["safe-join-contract"]
    assert "run_sql" in ARM_TOOLS["free-sql"]


def test_every_arm_is_offered_discovery_tools():
    """An arm that cannot discover the metrics would fail for reasons the
    experiment does not intend to measure."""
    for arm, tools in ARM_TOOLS.items():
        assert "list_metrics" in tools and "describe_metric" in tools, arm


# ----------------------------------------------------------------- behaviour


@live
def test_it_answers_a_plain_question_correctly():
    card = answer(QUESTIONS["q001"].text, SPEC.personas["FINANCE_GLOBAL"],
                  "strict-contract", CONTRACTS)
    got = sorted((r["REGION"], r["VALUE"]) for r in card.rows)
    expected = sorted((r["REGION"], r["VALUE"]) for r in _truth("q001", "FINANCE_GLOBAL"))
    assert got == expected
    assert card.metrics_used == ["bookings_amount@1"]
    assert card.query_id


@live
def test_it_refuses_an_ambiguous_question_instead_of_picking_one():
    """q007 names no metric. Bookings, billings and revenue all answer it with
    different numbers, so any confident single answer is wrong."""
    card = answer(QUESTIONS["q007"].text, SPEC.personas["FINANCE_GLOBAL"],
                  "strict-contract", CONTRACTS)
    assert card.rows == []
    assert card.why_not
    assert card.confidence == "none"


@live
def test_it_says_what_was_withheld_rather_than_returning_a_quiet_subset():
    """Asked for a region it cannot see, the agent must SAY so. A smaller
    number presented as complete is the dangerous failure."""
    card = answer(QUESTIONS["q012"].text, SPEC.personas["SALES_DIR_EMEA"],
                  "strict-contract", CONTRACTS)
    assert card.why_not, "returned a partial answer without saying anything was withheld"
    assert "AMER" in card.why_not


@live
def test_the_card_always_carries_provenance():
    card = answer(QUESTIONS["q002"].text, SPEC.personas["SALES_DIR_EMEA"],
                  "strict-contract", CONTRACTS)
    if not card.is_refusal:
        assert card.sql and card.query_id and card.lineage
        assert card.context["role"] == "GAA_SALES_DIR_EMEA"
