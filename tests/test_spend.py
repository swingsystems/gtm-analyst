"""What an answer cost to produce.

The threat model closes cost "on the warehouse side" -- statement timeout, row
cap, resource monitor -- and names model spend as the residual. Model spend is
precisely what was not measured: the first pilot recorded no usage at all, so
the only honest answer to "what did this cost" was an estimate from tool-call
counts. The rollout plan meanwhile lists credit cost per answer as a metric to
track. A project about auditable numbers should not have to guess its own bill.
"""
from decimal import Decimal

import pytest

from gtm_analyst.agent.spend import PRICES, Spend, price_of


def test_spend_accumulates_across_turns() -> None:
    """An agent loop is many API calls, not one. Recording only the last would
    under-report by roughly the number of turns."""
    s = Spend()
    s.add(input_tokens=1000, output_tokens=200)
    s.add(input_tokens=1500, output_tokens=300)
    assert s.input_tokens == 2500
    assert s.output_tokens == 500
    assert s.api_calls == 2


def test_cost_is_decimal_not_float() -> None:
    """Money is NUMBER(38,2) everywhere else in this project for a reason.
    Float dollars accumulate rounding artifacts indistinguishable from a real
    difference in spend."""
    cost = price_of("claude-sonnet-5", input_tokens=1_000_000, output_tokens=0)
    assert isinstance(cost, Decimal)
    assert cost == PRICES["claude-sonnet-5"].input_per_mtok


def test_input_and_output_are_priced_differently() -> None:
    """Output costs several times input. Summing them into one token count
    would understate the bill on exactly the calls that matter."""
    model = "claude-sonnet-5"
    assert price_of(model, 1_000_000, 0) != price_of(model, 0, 1_000_000)


def test_cache_reads_are_cheaper_than_fresh_input() -> None:
    """The agent loop resends a growing prompt every turn, so cache reads
    dominate a long run. Pricing them as fresh input overstates the cost."""
    model = "claude-sonnet-5"
    fresh = price_of(model, input_tokens=1_000_000, output_tokens=0)
    cached = price_of(model, input_tokens=0, output_tokens=0,
                      cache_read_tokens=1_000_000)
    assert cached < fresh


def test_an_unknown_model_refuses_rather_than_guessing() -> None:
    """A silent zero would report a run as free. Being unable to price something
    is information, not a default."""
    with pytest.raises(KeyError, match="no published price"):
        price_of("claude-not-a-real-model", 100, 100)


def test_spend_prices_itself() -> None:
    s = Spend(model="claude-sonnet-5")
    s.add(input_tokens=1_000_000, output_tokens=1_000_000)
    assert s.cost_usd == price_of("claude-sonnet-5", 1_000_000, 1_000_000)


def test_an_empty_spend_costs_nothing_and_says_so() -> None:
    """A mock or replayed run makes no API calls. Zero is the truth there, and
    must be distinguishable from 'not measured'."""
    s = Spend(model="claude-sonnet-5")
    assert s.api_calls == 0
    assert s.cost_usd == Decimal("0.00")


def test_usage_is_read_from_a_real_response_shape() -> None:
    """Anthropic returns usage on the response, and the cache fields are absent
    unless caching was used. Reading them with getattr defaults keeps a run
    from crashing on a response that simply did not cache."""
    class _Usage:
        input_tokens = 120
        output_tokens = 34

    class _Response:
        usage = _Usage()

    s = Spend(model="claude-sonnet-5")
    s.observe(_Response())
    assert (s.input_tokens, s.output_tokens, s.api_calls) == (120, 34, 1)


def test_cost_is_reported_separately_from_the_preregistered_summary() -> None:
    """summary.md's schema was fixed in ADR 0003 before any number existed.
    A cost section inside it would be a harmless-looking edit to a document
    whose whole value is that it was not edited after seeing results.
    """
    from gtm_analyst.harness.run import spend_report, summarise

    rendered = summarise([], ["free-sql"])
    assert "cost" not in rendered.lower()
    assert "usd" not in rendered.lower()
    assert "What this run cost" in spend_report([])


def test_unmeasured_cards_are_not_counted_as_free() -> None:
    """The 25 cards recorded before this existed cost real money. Treating a
    missing measurement as zero would report the most expensive run as free."""
    from gtm_analyst.harness.run import spend_report

    out = spend_report([{"arm": "free-sql", "spend": None}])
    assert "No usage recorded" in out
    assert "$0" not in out


def test_a_run_that_gave_up_still_reports_its_cost() -> None:
    """Turn exhaustion is the most expensive outcome -- a full budget spent for
    no answer. Omitting it would make the arm that quits look cheapest."""
    import inspect

    from gtm_analyst.agent import runner

    source = inspect.getsource(runner.answer)
    # Three construction sites: exhausted, no-query, and answered.
    assert source.count("spend=spend.as_dict()") == 3


def test_a_free_tier_model_costs_exactly_zero() -> None:
    """OpenRouter's ':free' suffix is a documented contract. Pricing it as a
    genuine zero keeps a free run distinguishable from one nobody could price."""
    from gtm_analyst.agent.spend import price_of

    assert price_of("nvidia/nemotron-3.5-lightning:free", 1_000_000, 1_000_000) == 0


def test_an_nvidia_model_is_not_assumed_free() -> None:
    """The build tier is free to evaluate, but that is not a per-model
    guarantee, and assuming zero is how a bill arrives as a surprise."""
    from gtm_analyst.agent.spend import price_of

    with pytest.raises(KeyError, match="no published price"):
        price_of("meta/llama-3.3-70b-instruct", 100, 100)


def test_an_unpriced_model_records_none_not_a_crash() -> None:
    """Raising here would make a working model unusable for a whole run just
    because nobody had looked up its rate -- a pricing gap taking down the
    experiment."""
    from gtm_analyst.agent.spend import Spend

    s = Spend(model="mistralai/mistral-nemotron")
    s.add(input_tokens=100, output_tokens=10)
    assert s.as_dict()["cost_usd"] is None


def test_an_unpriced_run_is_never_summed_as_free() -> None:
    """None is not zero. A run whose cost is unknown must stay visibly unknown."""
    from gtm_analyst.harness.run import spend_report

    out = spend_report([{"arm": "free-sql",
                         "spend": {"model": "x", "cost_usd": None, "api_calls": 3,
                                   "input_tokens": 1, "output_tokens": 1}}])
    assert "No usage recorded" in out
