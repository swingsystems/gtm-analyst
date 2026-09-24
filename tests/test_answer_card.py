"""The answer card is the deliverable, not the number.

An answer without provenance cannot be audited, and an architecture whose whole
claim is auditability must refuse to emit one.
"""
import pytest
from pydantic import ValidationError

from gaa.agent.card import AnswerCard


def _card(**overrides):
    base = {
        "question": "What were total bookings for Q3 2026 by region?",
        "persona": "FINANCE_GLOBAL",
        "arm": "strict-contract",
        "rows": [{"REGION": "EMEA", "VALUE": "4137843.49"}],
        "sql": "SELECT REGION, SUM(AMOUNT) AS VALUE FROM V_BOOKINGS WHERE FISCAL_QUARTER = ?",
        "metrics_used": ["bookings_amount@1"],
        "lineage": ["V_BOOKINGS"],
        "context": {"persona": "FINANCE_GLOBAL", "role": "GAA_FINANCE_GLOBAL",
                    "schema": "FINANCE"},
        "query_id": "01c74b11-010b-a854-000a-95d700bcc47a",
        "confidence": "high",
        "confidence_basis": "single declared metric, no ambiguity in the request",
    }
    base.update(overrides)
    return AnswerCard(**base)


def test_a_complete_card_builds():
    card = _card()
    assert card.query_id
    assert card.why_not is None


def test_an_answered_card_without_sql_is_refused():
    """A number with no statement behind it cannot be checked by anyone."""
    with pytest.raises(ValidationError):
        _card(sql="")


def test_an_answered_card_without_a_query_id_is_refused():
    """The query id is what ties the answer to a row in ACCOUNT_USAGE. Without
    it the audit trail stops at our own logs, which is where an auditor stops
    believing them."""
    with pytest.raises(ValidationError):
        _card(query_id=None)


def test_a_refusal_needs_no_sql_but_must_say_why():
    """Refusing is legitimate. Refusing silently is not."""
    card = AnswerCard(
        question="How much did we sell in Q3 2026?",
        persona="FINANCE_GLOBAL",
        arm="strict-contract",
        rows=[],
        sql=None,
        metrics_used=[],
        lineage=[],
        context={"persona": "FINANCE_GLOBAL", "role": "R", "schema": "S"},
        query_id=None,
        confidence="none",
        confidence_basis="question names no metric",
        why_not="'sell' is ambiguous: bookings, billings and revenue give different answers.",
    )
    assert card.is_refusal


def test_a_refusal_without_a_reason_is_refused():
    with pytest.raises(ValidationError, match="why_not"):
        AnswerCard(
            question="q", persona="P", arm="strict-contract", rows=[], sql=None,
            metrics_used=[], lineage=[], context={}, query_id=None,
            confidence="none", confidence_basis="b", why_not=None,
        )


def test_governance_withholding_is_recorded_even_when_rows_come_back():
    """A partial answer that does not say what was withheld is the dangerous
    case: it looks complete and is quietly smaller."""
    card = _card(
        persona="SALES_DIR_EMEA",
        rows=[{"REGION": "EMEA", "VALUE": "4137843.49"}],
        why_not="AMER and APAC withheld: this role is scoped to EMEA.",
    )
    assert not card.is_refusal
    assert "withheld" in card.why_not


def test_the_arm_is_constrained_to_known_values():
    with pytest.raises(ValidationError):
        _card(arm="whatever")


def test_markdown_renders_every_provenance_field():
    """This is what a reviewer reads. A field missing here is a field nobody
    checks."""
    rendered = _card(why_not="AMER withheld.").to_markdown()
    for expected in ["bookings_amount@1", "V_BOOKINGS", "GAA_FINANCE_GLOBAL",
                     "01c74b11", "AMER withheld", "SELECT REGION"]:
        assert expected in rendered, f"{expected!r} missing from the card"
