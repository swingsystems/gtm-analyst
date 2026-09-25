"""The no-account path.

Adoption dies at this gate. A reader must see a real answer card, a real
governance refusal, and a real evaluation report with NO Snowflake account and
NO API key -- and the cards must be genuine recordings, because a demo built on
invented output is a claim about behaviour nobody observed.
"""
from pathlib import Path

import pytest

from gtm_analyst.demo.run import DemoError, run_demo

CARDS = Path(__file__).parent.parent / "results" / "pilot2" / "cards.json"


def test_the_demo_runs_with_every_credential_stripped(monkeypatch, tmp_path):
    """The whole promise. If this ever reaches Snowflake or Anthropic, the
    five-minute claim is false and the tier-0 path is decoration."""
    for name in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH",
                 "SNOWFLAKE_SERVICE_USER_PREFIX", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = run_demo(CARDS, tmp_path)
    assert result.answer_card is not None
    assert result.refusal_card is not None
    assert (tmp_path / "summary.md").exists()


def test_the_demo_makes_no_network_calls(monkeypatch, tmp_path):
    """Asserted rather than assumed: any socket connection fails the test."""
    import socket

    def _refuse(*args, **kwargs):
        raise AssertionError("the demo attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    run_demo(CARDS, tmp_path)


def test_the_demo_shows_a_real_governance_refusal(tmp_path):
    """The argument, not a footnote. A card that withheld something must say
    what, or the demo shows an agent being quietly smaller."""
    result = run_demo(CARDS, tmp_path)
    assert result.refusal_card.why_not
    assert len(result.refusal_card.why_not) > 30


def test_the_demo_shows_the_same_question_answered_differently_per_persona(tmp_path):
    """The architecture in one screen. If every persona returns the same rows,
    the demo is showing nothing."""
    result = run_demo(CARDS, tmp_path)
    assert len(result.persona_comparison) >= 2
    row_counts = {p: len(c.rows) for p, c in result.persona_comparison.items()}
    assert len(set(row_counts.values())) > 1, f"all personas identical: {row_counts}"


def test_it_fails_loudly_when_the_recordings_are_missing(tmp_path):
    """Silently showing nothing would be worse than an error."""
    with pytest.raises(DemoError, match="no recorded"):
        run_demo(tmp_path / "nope.json", tmp_path)


@pytest.mark.skipif(not CARDS.exists(), reason="no recorded cards committed")
def test_the_committed_recordings_are_genuine():
    """Every card must carry a real Snowflake query id. An invented demo is the
    one thing this path cannot afford."""
    import json

    for card in json.loads(CARDS.read_text()):
        if card["sql"]:
            assert card["query_id"], f"{card['_question_id']} has SQL but no query id"


def test_the_rendered_totals_match_the_cards(tmp_path):
    """The first renderer matched anything digit-shaped and summed an account id
    into a money column, reporting 1,313,794.51 where the truth was
    1,313,784.51. A demo that misreports its own recordings is worse than no
    demo: it is a wrong number wearing the costume of provenance."""

    from gtm_analyst.harness.score import _numeric_total

    result = run_demo(CARDS, tmp_path)
    rendered = (tmp_path / "summary.md").read_text()
    for card in result.persona_comparison.values():
        expected = _numeric_total(card.rows)
        if expected:
            assert f"{expected:,.2f}" in rendered, (
                f"{card.persona}: rendered total does not match the card ({expected})"
            )


def test_totals_never_sum_an_identifier(tmp_path):
    """The specific bug. ACCOUNT_ID and FISCAL_QUARTER are not money."""
    from decimal import Decimal

    from gtm_analyst.harness.score import _numeric_total

    rows = [{"ACCOUNT_ID": "ACC00010", "REGION": "EMEA", "VALUE": "100.00"}]
    assert _numeric_total(rows) == Decimal("100.00")
