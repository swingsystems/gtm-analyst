"""The viewer renders recorded cards into one page. No server, no network.

The argument the page has to make is visual: the same question, asked by three
identities, returning three different correct answers. If the withholding is not
obvious at a glance the page has failed, so that is what these tests check.
"""
import json
from pathlib import Path

import pytest

from gtm_analyst.agent.card import AnswerCard
from gtm_analyst.viewer.build import build_page, cards_for_question, group_by_persona, load_cards

CARDS = Path(__file__).parent.parent / "results" / "pilot2" / "cards.json"


@pytest.fixture(scope="module")
def cards() -> list[AnswerCard]:
    return load_cards(CARDS)


def test_the_recorded_cards_still_validate(cards: list[AnswerCard]) -> None:
    """The viewer reads real recorded output, not fixtures. If the card schema
    drifts from what was recorded, the page is rendering something else."""
    assert len(cards) == 25


def test_the_three_personas_answering_one_question_are_found(cards: list[AnswerCard]) -> None:
    chosen = cards_for_question(cards, "excluding intercompany")
    by_persona = group_by_persona(chosen)
    assert set(by_persona) == {"FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL"}


def test_the_three_answers_actually_differ(cards: list[AnswerCard]) -> None:
    """If every persona returned the same rows the page would prove nothing.
    This is the claim the whole viewer exists to show, so it is asserted rather
    than assumed."""
    by_persona = group_by_persona(cards_for_question(cards, "excluding intercompany"))
    row_counts = {p: len(c.rows) for p, c in by_persona.items()}
    assert row_counts["FINANCE_GLOBAL"] > row_counts["REP_INDIVIDUAL"]
    assert len({json.dumps(c.rows, sort_keys=True) for c in by_persona.values()}) == 3


def test_a_restricted_persona_says_what_it_withheld(cards: list[AnswerCard]) -> None:
    by_persona = group_by_persona(cards_for_question(cards, "excluding intercompany"))
    assert by_persona["REP_INDIVIDUAL"].why_not
    assert by_persona["SALES_DIR_EMEA"].why_not


def test_the_page_renders_every_persona_and_its_provenance(cards: list[AnswerCard]) -> None:
    html = build_page(cards, "excluding intercompany")
    for persona in ("FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL"):
        assert persona in html
    # Provenance is the point of an answer card; a page omitting it is decoration.
    by_persona = group_by_persona(cards_for_question(cards, "excluding intercompany"))
    assert by_persona["FINANCE_GLOBAL"].query_id in html
    assert "V_BOOKINGS" in html


def test_withheld_text_is_rendered_not_just_flagged(cards: list[AnswerCard]) -> None:
    html = build_page(cards, "excluding intercompany")
    why = group_by_persona(cards_for_question(cards, "excluding intercompany"))[
        "REP_INDIVIDUAL"].why_not
    assert why is not None
    # The first clause is enough; the full string may be long.
    assert why.split(".")[0][:40] in html


def test_the_page_is_self_contained(cards: list[AnswerCard]) -> None:
    """It has to open from disk with no account, no key and no network -- same
    constraint as the demo. A CDN stylesheet would break that silently, looking
    fine on the machine that built it."""
    html = build_page(cards, "excluding intercompany")
    assert "http://" not in html
    assert "https://" not in html
    assert "<script" not in html.lower()


def test_sql_is_escaped_rather_than_interpolated(cards: list[AnswerCard]) -> None:
    """Card content is rendered into HTML. It comes from a model, so it is
    untrusted text, and '<' must survive as text rather than becoming a tag."""
    record = json.loads(CARDS.read_text())[0]
    hostile = AnswerCard.model_validate(
        {k: v for k, v in record.items() if not k.startswith("_")}
        | {"question": "<img src=x onerror=alert(1)>"}
    )
    html = build_page([hostile], "<img")
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_an_unknown_question_fails_loudly(cards: list[AnswerCard]) -> None:
    """Rendering an empty page would look like a viewer bug, not a typo."""
    with pytest.raises(ValueError, match="matched no recorded"):
        build_page(cards, "a question nobody asked")
