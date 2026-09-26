"""Two grids, side by side, never summed.

ADR 0007 forbids merging cells from different models: an observed arm difference
would be indistinguishable from a model difference. A reader still needs to see
both results, so this renders them as separate rows and refuses the merge in
code rather than trusting whoever runs it.

It also refuses to compare accuracy across question sets that are not the same.
Doing so reads as a like-for-like result and is not one -- the same error as
reporting a single accuracy figure over two arms with different coverage, which
the pre-registered schema already forbids for exactly this reason.
"""
from decimal import Decimal
from typing import Any


def grid_summary(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe one grid, refusing one that contains more than one model."""
    if not cards:
        raise ValueError("no cards: refusing to summarise an empty grid as zero")

    models = {(c.get("spend") or {}).get("model") for c in cards}
    models.discard(None)
    if len(models) > 1:
        raise ValueError(
            f"this grid contains more than one model ({sorted(models)}). "
            f"ADR 0007 forbids it: an arm difference would be "
            f"indistinguishable from a model difference"
        )

    spends = [c["spend"] for c in cards if c.get("spend")]
    return {
        "model": next(iter(models)) if models else "unrecorded",
        "cells": len(cards),
        "questions": len({c["_question_id"] for c in cards}),
        "question_ids": sorted({c["_question_id"] for c in cards}),
        "personas": len({c["persona"] for c in cards}),
        "arms": sorted({c["arm"] for c in cards}),
        "api_calls": sum(s.get("api_calls", 0) for s in spends),
        "cost_usd": sum((Decimal(s.get("cost_usd", "0")) for s in spends), Decimal(0)),
        "measured": len(spends),
    }


def compare_grids(grids: dict[str, list[dict[str, Any]]]) -> str:
    """Render two or more grids as separate rows.

    Deliberately produces no combined total. If a reader can find one, the
    separation has failed.
    """
    if len(grids) < 2:
        raise ValueError("a comparison needs at least two grids; one is a summary")

    summaries = {name: grid_summary(cards) for name, cards in grids.items()}

    lines = ["# Two grids, reported separately", ""]
    lines += [
        ("Cells from different models are never merged. An arm difference would "
         "otherwise be indistinguishable from a model difference — see "
         "`docs/adr/0007-two-providers-never-one-grid.md`. There is deliberately "
         "no combined figure below."),
        "",
        "| grid | model | cells | questions | arms | API calls | USD |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in summaries.items():
        lines.append(
            f"| {name} | `{s['model']}` | {s['cells']} | {s['questions']} | "
            f"{len(s['arms'])} | {s['api_calls']} | {s['cost_usd']} |"
        )

    # Coverage differences, stated rather than averaged away.
    shared = set.intersection(*(set(s["question_ids"]) for s in summaries.values()))
    shared_note = (
        f"**Questions both grids cover: {len(shared)}** "
        f"({', '.join(sorted(shared)) or 'none'}). Only these support a "
        f"like-for-like arm comparison across models."
    )
    lines += ["", shared_note]

    for name, s in summaries.items():
        only = sorted(set(s["question_ids"]) - shared)
        if only:
            only_note = (
                f"Covered **only** by {name}, and therefore **not comparable** "
                f"across models: {', '.join(only)}."
            )
            lines += ["", only_note]

    unmeasured = {n: s["cells"] - s["measured"] for n, s in summaries.items()
                  if s["cells"] != s["measured"]}
    if unmeasured:
        detail = ", ".join(f"{n} {c}" for n, c in unmeasured.items())
        lines += ["", (
            "Cells with no recorded spend (they predate cost measurement, and "
            f"are not free): {detail}."
        )]

    return "\n".join(lines) + "\n"
