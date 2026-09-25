"""The deterministic replay agent.

Tier 0 of the adoption path: a reader with no Snowflake account and no API key
runs `make demo` and sees real answer cards, real governance refusals and a real
eval report. The cards are genuine -- recorded from live runs, not invented --
which is the only reason showing them proves anything.
"""
import json
from pathlib import Path

import pytest

from gtm_analyst.agent.card import AnswerCard
from gtm_analyst.agent.mock import MockAgent, record_run

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mock_runs"


def _card(**overrides):
    base = {
        "question": "What were total bookings for Q3 2026 by region?",
        "persona": "FINANCE_GLOBAL", "arm": "strict-contract",
        "rows": [{"REGION": "EMEA", "VALUE": "4137843.49"}],
        "sql": "SELECT REGION, SUM(AMOUNT) AS VALUE FROM V_BOOKINGS WHERE FISCAL_QUARTER = ?",
        "metrics_used": ["bookings_amount@1"], "lineage": ["V_BOOKINGS"],
        "context": {"persona": "FINANCE_GLOBAL", "role": "GAA_FINANCE_GLOBAL",
                    "schema": "FINANCE"},
        "query_id": "01c74b11-010b-a854-000a-95d700bcc47a",
        "confidence": "high", "confidence_basis": "single declared metric",
    }
    base.update(overrides)
    return AnswerCard(**base)


def test_a_recorded_run_replays_identically(tmp_path):
    original = _card()
    record_run(tmp_path, "q001", original)
    replayed = MockAgent(tmp_path).answer("q001", "FINANCE_GLOBAL", "strict-contract")
    assert replayed == original


def test_replay_needs_no_credentials(tmp_path, monkeypatch):
    """The point of tier 0. If this ever reaches Snowflake or Anthropic, the
    no-account path is a fiction and the five-minute promise is false."""
    record_run(tmp_path, "q001", _card())
    for name in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "ANTHROPIC_API_KEY",
                 "SNOWFLAKE_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(name, raising=False)
    assert MockAgent(tmp_path).answer("q001", "FINANCE_GLOBAL", "strict-contract").rows


def test_an_unrecorded_question_raises_rather_than_inventing_one(tmp_path):
    """A mock that fabricates an answer turns the demo into a lie about what
    the system does."""
    record_run(tmp_path, "q001", _card())
    with pytest.raises(KeyError, match="q999"):
        MockAgent(tmp_path).answer("q999", "FINANCE_GLOBAL", "strict-contract")


def test_the_three_arms_are_recorded_separately(tmp_path):
    record_run(tmp_path, "q011", _card(arm="strict-contract", rows=[], sql=None,
                                       query_id=None, confidence="none",
                                       confidence_basis="no dimension",
                                       why_not="territory is not a declared dimension"))
    record_run(tmp_path, "q011", _card(arm="safe-join-contract"))
    agent = MockAgent(tmp_path)
    assert agent.answer("q011", "FINANCE_GLOBAL", "strict-contract").is_refusal
    assert not agent.answer("q011", "FINANCE_GLOBAL", "safe-join-contract").is_refusal


def test_a_governance_refusal_replays_with_its_reason(tmp_path):
    record_run(tmp_path, "q012", _card(
        persona="SALES_DIR_EMEA",
        why_not="AMER and APAC withheld: this role is scoped to EMEA."))
    card = MockAgent(tmp_path).answer("q012", "SALES_DIR_EMEA", "strict-contract")
    assert "withheld" in card.why_not


def test_recorded_fixtures_are_readable_json(tmp_path):
    """They are committed and reviewed, so they have to be legible rather than
    a pickled blob nobody can audit."""
    record_run(tmp_path, "q001", _card())
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    assert payload["question"] and payload["sql"]


def test_the_committed_fixtures_load_if_present():
    if not FIXTURES.exists() or not any(FIXTURES.glob("*.json")):
        pytest.skip("no fixtures recorded yet")
    agent = MockAgent(FIXTURES)
    assert agent.recorded, "fixture directory present but nothing loadable in it"
    for card in agent.recorded.values():
        assert isinstance(card, AnswerCard)
