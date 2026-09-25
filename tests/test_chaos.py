"""Every planted defect must be caught. CI requires 100%.

Slow: each variant rebuilds models against the live warehouse and runs the
reference suite. Skipped without credentials.
"""
import os
from pathlib import Path

import pytest

from gaa.harness.chaos import VARIANTS, chaos, dbt_tests_pass
from gaa.runner.reference import run_reference
from gaa.spec.loader import load_spec

SPEC_ROOT = Path(__file__).parent.parent / "evals" / "spec"
SPEC = load_spec(SPEC_ROOT)
QUESTIONS = {q.id: q for q in SPEC.questions}

live = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)


def _matches_ground_truth(question_id: str, persona_name: str) -> bool:
    question = QUESTIONS[question_id]
    persona = SPEC.personas[persona_name]
    expected = next(e.rows for e in question.expected if e.persona == persona_name)
    actual = run_reference(SPEC_ROOT, question, persona).rows
    return actual == expected


def test_every_variant_declares_what_should_catch_it():
    """A variant nobody knows how to detect is decoration."""
    for name, variant in VARIANTS.items():
        assert variant.caught_by, name
        assert variant.target.exists(), f"{name} targets a model that does not exist"
        assert (Path(__file__).parent.parent / "chaos" / f"{name}.sql").exists(), name


@live
def test_the_harness_agrees_with_ground_truth_before_any_chaos():
    """The control. If this fails, a later catch proves nothing."""
    assert _matches_ground_truth("q010", "FINANCE_GLOBAL")
    assert _matches_ground_truth("q002", "FINANCE_GLOBAL")


@live
def test_calendar_too_short_is_caught():
    """The bug this project actually shipped, in e517ed4."""
    with chaos("calendar_too_short"):
        assert not dbt_tests_pass(), "a calendar that drops revenue rows went unnoticed"
    assert dbt_tests_pass(), "the warehouse was left broken"


@live
def test_coalesce_swallows_null_is_caught():
    """Totals still reconcile, which is what makes it dangerous. Only the
    grouping changes, and only q010 looks at the grouping."""
    with chaos("coalesce_swallows_null"):
        assert not _matches_ground_truth("q010", "FINANCE_GLOBAL"), (
            "the null segment vanished into SMB and q010 did not notice"
        )
    assert _matches_ground_truth("q010", "FINANCE_GLOBAL"), "chaos was not reverted"


@live
def test_fanout_join_is_caught():
    """The crude version of the failure the strict arm exists to prevent: a
    join missing the predicate that makes it a join. BOOKING_ID stops being
    unique, so dbt catches this one before any question is asked."""
    with chaos("fanout_join"):
        assert not dbt_tests_pass(), "a near-cross-product left BOOKING_ID unique"
    assert dbt_tests_pass(), "the warehouse was left broken"


@live
def test_wrong_effective_date_is_caught():
    """The mirror image of a bug this project shipped. Consumers read the
    validity window half-open; pushing VALID_TO out by a day puts every
    handover date inside two assignments at once."""
    with chaos("wrong_effective_date"):
        assert not _matches_ground_truth("q011", "FINANCE_GLOBAL"), (
            "a booking counted in two territories at once went unnoticed"
        )
    assert _matches_ground_truth("q011", "FINANCE_GLOBAL"), "chaos was not reverted"


@live
def test_off_by_one_quarter_is_caught_but_not_by_the_question_predicted():
    """The prediction in chaos/README.md was q008. It was wrong, and the test
    says so rather than being quietly retargeted.

    q008 asks which bookings landed on the last day of Q2 and filters on
    BOOKING_DATE, never reading FISCAL_QUARTER -- so shifting every quarter
    label leaves it perfectly correct. q001 filters on FISCAL_QUARTER and moves.

    Worth keeping as a test rather than a footnote: a planted defect and the
    detector that was supposed to catch it were chosen by the same person on the
    same day, and one of them was wrong.
    """
    with chaos("off_by_one_quarter"):
        assert _matches_ground_truth("q008", "FINANCE_GLOBAL"), (
            "q008 was expected to be blind to this; if it now moves, the "
            "reasoning above is stale"
        )
        assert not _matches_ground_truth("q001", "FINANCE_GLOBAL"), (
            "a quarter boundary shifted by a day did not move any Q3 total"
        )
    assert _matches_ground_truth("q001", "FINANCE_GLOBAL"), "chaos was not reverted"


@live
def test_the_catch_rate_is_total():
    """The number CI gates on. Reported rather than assumed."""
    caught = []
    with chaos("calendar_too_short"):
        caught.append(not dbt_tests_pass())
    with chaos("coalesce_swallows_null"):
        caught.append(not _matches_ground_truth("q010", "FINANCE_GLOBAL"))
    with chaos("fanout_join"):
        caught.append(not dbt_tests_pass())
    with chaos("wrong_effective_date"):
        caught.append(not _matches_ground_truth("q011", "FINANCE_GLOBAL"))
    with chaos("off_by_one_quarter"):
        caught.append(not _matches_ground_truth("q001", "FINANCE_GLOBAL"))
    assert all(caught), f"catch rate {sum(caught)}/{len(caught)}"
