"""What an answer cost to produce.

The threat model closes cost on the warehouse side -- statement timeout, row
cap, resource monitor -- and names model spend as the residual. That residual
was unmeasured: the pilots recorded no usage at all, so the only answer to "what
did this cost" was an estimate from tool-call counts. The rollout plan lists
credit cost per answer as a metric to track, and a project about auditable
numbers should not have to guess its own bill.

Money is Decimal here for the same reason it is NUMBER(38,2) in the warehouse.
Float dollars accumulate rounding artifacts that are indistinguishable from a
real difference in spend, which is the whole failure this project keeps finding
in other forms.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Published rates, recorded so a run can price
    itself without a network call."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cache_write_per_mtok: Decimal
    cache_read_per_mtok: Decimal


# Rates as published for these models. Kept as a table rather than fetched: a
# recorded run must be re-pricable later at the rate that applied, and a cost
# that silently changes when a price list does is not an audit trail.
PRICES: dict[str, Price] = {
    "claude-sonnet-5": Price(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_write_per_mtok=Decimal("3.75"),
        cache_read_per_mtok=Decimal("0.30"),
    ),
    "claude-opus-5": Price(
        input_per_mtok=Decimal("15.00"),
        output_per_mtok=Decimal("75.00"),
        cache_write_per_mtok=Decimal("18.75"),
        cache_read_per_mtok=Decimal("1.50"),
    ),
    "claude-haiku-4-5-20251001": Price(
        input_per_mtok=Decimal("1.00"),
        output_per_mtok=Decimal("5.00"),
        cache_write_per_mtok=Decimal("1.25"),
        cache_read_per_mtok=Decimal("0.10"),
    ),
}

_MILLION = Decimal(1_000_000)


def price_of(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> Decimal:
    """Cost in USD, rounded to the cent.

    Raises on an unknown model rather than returning zero. A silent zero reports
    a run as free, and being unable to price something is information rather
    than a default.
    """
    try:
        price = PRICES[model]
    except KeyError:
        raise KeyError(
            f"no published price recorded for {model!r}; add it to PRICES rather "
            f"than letting a run report as free"
        ) from None

    total = (
        Decimal(input_tokens) * price.input_per_mtok
        + Decimal(output_tokens) * price.output_per_mtok
        + Decimal(cache_write_tokens) * price.cache_write_per_mtok
        + Decimal(cache_read_tokens) * price.cache_read_per_mtok
    ) / _MILLION
    return total.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass
class Spend:
    """Token usage accumulated across one agent loop.

    An agent loop is many API calls, not one -- the recorded pilot averaged nine
    tool calls per answer. Recording only the final response would under-report
    by roughly the number of turns.
    """

    model: str = "claude-sonnet-5"
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    _unpriceable: bool = field(default=False, repr=False)

    def add(self, input_tokens: int = 0, output_tokens: int = 0,
            cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> None:
        self.api_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_write_tokens += cache_write_tokens
        self.cache_read_tokens += cache_read_tokens

    def observe(self, response: Any) -> None:
        """Record usage from an Anthropic response.

        The cache fields are absent unless caching was used, so they are read
        with defaults -- a run must not crash because it happened not to cache.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.add(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )

    @property
    def cost_usd(self) -> Decimal:
        """Zero when nothing was called -- a replayed or mock run really is
        free, and that must stay distinguishable from 'not measured'."""
        if self.api_calls == 0:
            return Decimal("0.00")
        return price_of(self.model, self.input_tokens, self.output_tokens,
                        self.cache_write_tokens, self.cache_read_tokens)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "api_calls": self.api_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cost_usd": str(self.cost_usd),
        }
