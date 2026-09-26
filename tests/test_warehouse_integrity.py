"""A run that cannot trust its warehouse must stop, not record numbers.

This is not hypothetical. A 108-cell grid was run while CI was applying chaos
variants to the same Snowflake database, and one cell recorded 461,925,638.35
against a ground truth of 1,032,569.31 -- a 447x fan-out. The agent's own SQL
was correct; re-running it afterwards returned the right answer. The warehouse
had been deliberately broken underneath it, and nothing noticed.

Worse, it was nearly reported as a finding about the model. A number that
extreme looked like the fan-out trap firing, which is exactly the result the
experiment was hoping to observe -- the most dangerous kind of contamination is
the kind that confirms your thesis.
"""
import pytest

from gtm_analyst.harness.integrity import (
    CANARY,
    WarehouseChanged,
    verify_ground_truth,
)


def test_a_canary_is_declared() -> None:
    """A question and persona whose frozen expected rows are the fingerprint of
    a healthy warehouse."""
    question_id, persona = CANARY
    assert question_id and persona


def test_matching_ground_truth_passes() -> None:
    verify_ground_truth(lambda: [{"VALUE": "100.00"}], [{"VALUE": "100.00"}])


def test_a_changed_total_halts_the_run() -> None:
    """Halt, not warn. A warning scrolls past and the remaining cells are
    recorded as if nothing happened."""
    with pytest.raises(WarehouseChanged, match="no longer matches"):
        verify_ground_truth(lambda: [{"VALUE": "461925638.35"}], [{"VALUE": "1032569.31"}])


def test_a_changed_row_count_halts_the_run() -> None:
    """A dropped group is the quieter failure: totals can still reconcile while
    a whole segment has vanished."""
    with pytest.raises(WarehouseChanged):
        verify_ground_truth(lambda: [{"V": "1"}], [{"V": "1"}, {"V": "2"}])


def test_the_error_names_the_likely_cause() -> None:
    """Whoever sees this needs to know to look for a concurrent chaos run, not
    to start debugging the agent."""
    with pytest.raises(WarehouseChanged, match="chaos|concurrent|rebuilt"):
        verify_ground_truth(lambda: [{"V": "9"}], [{"V": "1"}])


def test_a_query_failure_is_not_silently_treated_as_healthy() -> None:
    """Returning nothing must not read as 'nothing changed'."""
    def broken():
        raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError, match="connection reset"):
        verify_ground_truth(broken, [{"V": "1"}])
