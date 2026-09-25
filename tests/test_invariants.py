"""Unit tests for the invariant checker, using synthetic results.

These deliberately do not touch Snowflake: an invariant that only works against
one particular dataset is not an invariant.
"""
from gtm_analyst.runner.invariants import check_invariant
from gtm_analyst.runner.reference import ReferenceResult
from gtm_analyst.spec.models import Invariant


def _res(qid, persona, rows):
    return ReferenceResult(qid, persona, rows, "qid-1")


SUM_OF_PARTS = Invariant(
    id="s", description="d", kind="sum_of_parts",
    params={"question_id": "q001", "whole_persona": "FINANCE_GLOBAL", "value_column": "VALUE",
            "part_column": "REGION", "parts": ["EMEA", "AMER", "APAC"]},
)
NESTING = Invariant(
    id="m", description="d", kind="monotonic_nesting",
    params={"question_id": "q002", "value_column": "VALUE",
            "order": ["REP_INDIVIDUAL", "SALES_DIR_EMEA", "FINANCE_GLOBAL"]},
)
MASKING = Invariant(
    id="k", description="d", kind="masking_preserves_row_count",
    params={"question_id": "q009", "personas": ["FINANCE_GLOBAL", "SALES_DIR_EMEA"],
            "masked_column": "ACCOUNT_NAME"},
)


def test_sum_of_parts_passes_when_every_part_is_present():
    results = {("q001", "FINANCE_GLOBAL"): _res("q001", "FINANCE_GLOBAL", [
        {"REGION": "EMEA", "VALUE": "10.00"},
        {"REGION": "AMER", "VALUE": "20.00"},
        {"REGION": "APAC", "VALUE": "30.00"}])}
    assert check_invariant(SUM_OF_PARTS, results).passed


def test_sum_of_parts_fails_when_a_region_silently_vanishes():
    """The failure this catches: a join or filter drops a whole region and the
    remaining total still looks like a plausible number."""
    results = {("q001", "FINANCE_GLOBAL"): _res("q001", "FINANCE_GLOBAL", [
        {"REGION": "EMEA", "VALUE": "10.00"},
        {"REGION": "AMER", "VALUE": "20.00"}])}
    outcome = check_invariant(SUM_OF_PARTS, results)
    assert not outcome.passed
    assert "APAC" in outcome.detail


def test_monotonic_nesting_passes_when_properly_nested():
    results = {
        ("q002", "REP_INDIVIDUAL"): _res("q002", "REP_INDIVIDUAL", [{"VALUE": "5.00"}]),
        ("q002", "SALES_DIR_EMEA"): _res("q002", "SALES_DIR_EMEA", [{"VALUE": "50.00"}]),
        ("q002", "FINANCE_GLOBAL"): _res("q002", "FINANCE_GLOBAL", [{"VALUE": "500.00"}]),
    }
    assert check_invariant(NESTING, results).passed


def test_monotonic_nesting_fails_on_a_leak():
    """A rep returning the global number is exactly the leak this detects."""
    results = {
        ("q002", "REP_INDIVIDUAL"): _res("q002", "REP_INDIVIDUAL", [{"VALUE": "500.00"}]),
        ("q002", "SALES_DIR_EMEA"): _res("q002", "SALES_DIR_EMEA", [{"VALUE": "50.00"}]),
        ("q002", "FINANCE_GLOBAL"): _res("q002", "FINANCE_GLOBAL", [{"VALUE": "500.00"}]),
    }
    outcome = check_invariant(NESTING, results)
    assert not outcome.passed
    assert "REP_INDIVIDUAL" in outcome.detail


def test_masking_preserves_row_count_passes():
    results = {
        ("q009", "FINANCE_GLOBAL"): _res("q009", "FINANCE_GLOBAL",
                                         [{"ACCOUNT_NAME": "Real A"}, {"ACCOUNT_NAME": "Real B"}]),
        ("q009", "SALES_DIR_EMEA"): _res("q009", "SALES_DIR_EMEA",
                                         [{"ACCOUNT_NAME": "ACCOUNT-1"},
                                          {"ACCOUNT_NAME": "ACCOUNT-2"}]),
    }
    assert check_invariant(MASKING, results).passed


def test_masking_fails_if_it_drops_rows():
    """Masking that filters is not masking. It would understate every total."""
    results = {
        ("q009", "FINANCE_GLOBAL"): _res("q009", "FINANCE_GLOBAL",
                                         [{"ACCOUNT_NAME": "A"}, {"ACCOUNT_NAME": "B"}]),
        ("q009", "SALES_DIR_EMEA"): _res("q009", "SALES_DIR_EMEA", [{"ACCOUNT_NAME": "X"}]),
    }
    assert not check_invariant(MASKING, results).passed


def test_masking_fails_if_names_come_through_unmasked():
    results = {
        ("q009", "FINANCE_GLOBAL"): _res("q009", "FINANCE_GLOBAL", [{"ACCOUNT_NAME": "Real A"}]),
        ("q009", "SALES_DIR_EMEA"): _res("q009", "SALES_DIR_EMEA", [{"ACCOUNT_NAME": "Real A"}]),
    }
    outcome = check_invariant(MASKING, results)
    assert not outcome.passed
    assert "identical" in outcome.detail
