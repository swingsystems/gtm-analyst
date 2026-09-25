"""The experiment runner and its report.

The reporting schema is as much the deliverable as the numbers. A summary
missing a required section fails here, because the schema was pre-registered
and a report that quietly drops a section is the misleading result ADR 0003
exists to prevent.
"""
from gaa.harness.run import summarise
from gaa.harness.score import Outcome, RefusalKind, Score
from gaa.spec.taxonomy import FailureCategory

ARMS = ["strict-contract", "safe-join-contract", "free-sql"]


def _score(qid, persona, arm, outcome, category=None, refusal=RefusalKind.NONE):
    return Score(question_id=qid, persona=persona, arm=arm, outcome=outcome,
                 category=category, refusal_kind=refusal, detail="d")


def _sample():
    scores = []
    for arm in ARMS:
        scores.append(_score("q001", "FINANCE_GLOBAL", arm, Outcome.CORRECT))
    scores.append(_score("q011", "FINANCE_GLOBAL", "strict-contract",
                         Outcome.INEXPRESSIBLE, refusal=RefusalKind.CAPABILITY))
    scores.append(_score("q011", "FINANCE_GLOBAL", "safe-join-contract", Outcome.CORRECT))
    scores.append(_score("q011", "FINANCE_GLOBAL", "free-sql", Outcome.WRONG,
                         FailureCategory.FANOUT_DOUBLE_COUNT))
    return scores


def test_the_report_contains_every_pre_registered_section():
    report = summarise(_sample(), ARMS)
    for section in ["Coverage and conditional accuracy", "Refusals, by kind",
                    "Head to head", "Safety bonus", "Failure categories", "Every cell"]:
        assert section in report, f"missing pre-registered section: {section}"


def test_no_single_aggregate_accuracy_is_emitted():
    """The specific thing ADR 0003 forbids. A reader who sees one number will
    average the arms in their head and conclude the wrong thing."""
    report = summarise(_sample(), ARMS).lower()
    assert "overall accuracy" not in report
    assert "total accuracy" not in report


def test_inexpressible_is_excluded_from_conditional_accuracy():
    """An arm is not credited for questions it declined to attempt, and not
    penalised for them either. Both would be wrong."""
    report = summarise(_sample(), ARMS)
    strict = next(line for line in report.splitlines()
                  if line.startswith("| strict-contract |") and "/" in line)
    assert "1/2" in strict, f"coverage should show 1 of 2 attempted: {strict}"


def test_the_head_to_head_uses_only_questions_every_arm_could_express():
    report = summarise(_sample(), ARMS)
    section = report.split("## Head to head")[1].split("##")[0]
    assert "q001" in section and "q011" not in section


def test_refusal_kinds_are_never_summed_into_one_number():
    report = summarise(_sample(), ARMS)
    section = report.split("## Refusals, by kind")[1].split("##")[0]
    assert "appropriate" in section and "capability" in section


def test_every_cell_appears_individually():
    """Row-level visibility. An aggregate hides the asymmetry between arms."""
    report = summarise(_sample(), ARMS)
    assert report.count("| q011 |") == 3
