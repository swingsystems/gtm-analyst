"""Reporting two grids side by side without merging them.

ADR 0007 forbids merging cells from different models: an arm difference would
become indistinguishable from a model difference. But a reader still needs to
see both, and the comparison has to refuse the thing the ADR forbids rather
than trusting whoever runs it.
"""
import pytest

from gtm_analyst.harness.compare import compare_grids, grid_summary


def _cards(model: str, questions: list[str], arms: list[str]) -> list[dict]:
    return [
        {"_question_id": q, "persona": p, "arm": a,
         "spend": {"model": model, "cost_usd": "0.01", "api_calls": 4,
                   "input_tokens": 100, "output_tokens": 10}}
        for q in questions for p in ("FINANCE_GLOBAL", "SALES_DIR_EMEA") for a in arms
    ]


def test_a_grid_reports_its_own_model_and_coverage() -> None:
    s = grid_summary(_cards("gpt-4.1", ["q001", "q002"], ["free-sql"]))
    assert s["model"] == "gpt-4.1"
    assert s["cells"] == 4
    assert s["questions"] == 2


def test_a_grid_containing_two_models_is_refused() -> None:
    """The failure ADR 0007 exists to prevent. Summarising it silently would
    hand a reader a number built from two different systems."""
    mixed = _cards("gpt-4.1", ["q001"], ["free-sql"]) + _cards(
        "claude-sonnet-5", ["q002"], ["free-sql"])
    with pytest.raises(ValueError, match="more than one model"):
        grid_summary(mixed)


def test_comparison_keeps_the_grids_separate() -> None:
    """One table row per grid and no summed row.

    Asserted structurally rather than by keyword. The first version of this test
    searched the text for "combined" and failed on the sentence explaining that
    there is deliberately no combined figure -- a test that a document must not
    discuss the thing it refuses to do.
    """
    a = _cards("gpt-4.1", ["q001", "q002"], ["free-sql", "strict-contract"])
    b = _cards("claude-sonnet-5", ["q001"], ["free-sql"])
    out = compare_grids({"openai": a, "claude": b})
    assert "gpt-4.1" in out and "claude-sonnet-5" in out

    # Data rows are the pipe-delimited lines after the header separator.
    rows = [ln for ln in out.splitlines()
            if ln.startswith("| ") and "---" not in ln and not ln.startswith("| grid")]
    assert len(rows) == 2, rows
    assert not any(ln.lower().startswith(("| total", "| all", "| sum")) for ln in rows)


def test_comparison_says_which_cells_only_one_grid_covers() -> None:
    """Comparing accuracy over different question sets is the same error as a
    single accuracy figure over different coverage -- it reads as a like-for-
    like result and is not one."""
    a = _cards("gpt-4.1", ["q001", "q002", "q003"], ["free-sql"])
    b = _cards("claude-sonnet-5", ["q001"], ["free-sql"])
    out = compare_grids({"openai": a, "claude": b})
    assert "q002" in out and "q003" in out
    assert "not comparable" in out.lower() or "only" in out.lower()


def test_comparison_refuses_a_single_grid() -> None:
    """A comparison of one thing is a summary wearing the wrong label."""
    with pytest.raises(ValueError, match="at least two"):
        compare_grids({"openai": _cards("gpt-4.1", ["q001"], ["free-sql"])})


def test_an_empty_grid_is_refused_rather_than_shown_as_zero() -> None:
    with pytest.raises(ValueError, match="no cards"):
        grid_summary([])
