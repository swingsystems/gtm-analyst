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
def test_the_catch_rate_is_total():
    """The number CI gates on. Reported rather than assumed."""
    caught = []
    with chaos("calendar_too_short"):
        caught.append(not dbt_tests_pass())
    with chaos("coalesce_swallows_null"):
        caught.append(not _matches_ground_truth("q010", "FINANCE_GLOBAL"))
    assert all(caught), f"catch rate {sum(caught)}/{len(caught)}"
