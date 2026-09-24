"""Metamorphic invariants: properties that hold regardless of the numbers.

Ground truth written by the same author who wrote the models can be confidently
wrong. These check relationships instead of values, so they fail on a mistaken
oracle that a value-by-value comparison would happily certify.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import pairwise

from gaa.runner.reference import ReferenceResult
from gaa.spec.models import Invariant

Results = dict[tuple[str, str], ReferenceResult]


@dataclass(frozen=True)
class InvariantResult:
    invariant_id: str
    passed: bool
    detail: str


def _total(rows: list[dict[str, str]], column: str) -> Decimal:
    total = Decimal(0)
    for row in rows:
        try:
            total += Decimal(row.get(column) or "0")
        except InvalidOperation:  # a non-numeric column contributes nothing
            continue
    return total


def _sum_of_parts(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    result = results.get((p["question_id"], p["whole_persona"]))
    if result is None:
        return InvariantResult(inv.id, False, f"no result for {p['question_id']}")

    seen = {row[p["part_column"]] for row in result.rows}
    missing = [part for part in p["parts"] if part not in seen]
    if missing:
        return InvariantResult(inv.id, False, f"missing parts: {', '.join(missing)}")

    whole = _total(result.rows, p["value_column"])
    parts = _total(
        [r for r in result.rows if r[p["part_column"]] in p["parts"]], p["value_column"]
    )
    if whole != parts:
        return InvariantResult(inv.id, False, f"whole {whole} != sum of parts {parts}")
    return InvariantResult(inv.id, True, f"all parts present, whole == parts == {whole}")


def _monotonic_nesting(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    totals = []
    for persona in p["order"]:
        result = results.get((p["question_id"], persona))
        if result is None:
            return InvariantResult(inv.id, False, f"no result for {persona}")
        totals.append((persona, _total(result.rows, p["value_column"])))

    for (lo_name, lo), (hi_name, hi) in pairwise(totals):
        if lo > hi:
            return InvariantResult(inv.id, False, f"{lo_name} ({lo}) exceeds {hi_name} ({hi})")
    return InvariantResult(inv.id, True, " <= ".join(f"{n}:{v}" for n, v in totals))


def _masking_preserves_row_count(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    counts, distincts = {}, {}
    for persona in p["personas"]:
        result = results.get((p["question_id"], persona))
        if result is None:
            return InvariantResult(inv.id, False, f"no result for {persona}")
        counts[persona] = len(result.rows)
        distincts[persona] = {row[p["masked_column"]] for row in result.rows}

    if len(set(counts.values())) != 1:
        return InvariantResult(inv.id, False, f"row counts differ: {counts}")
    values = list(distincts.values())
    if values[0] == values[1]:
        return InvariantResult(inv.id, False, "masked and unmasked values are identical")
    return InvariantResult(
        inv.id, True, f"row count {next(iter(counts.values()))} preserved, values differ"
    )


def _determinism(inv: Invariant, results: Results) -> InvariantResult:
    # Asserted by the runner executing each question twice and comparing; there
    # is nothing to compute from a single pass.
    return InvariantResult(inv.id, True, "checked by repeated execution in the runner")


_HANDLERS = {
    "sum_of_parts": _sum_of_parts,
    "monotonic_nesting": _monotonic_nesting,
    "masking_preserves_row_count": _masking_preserves_row_count,
    "determinism": _determinism,
}


def check_invariant(inv: Invariant, results: Results) -> InvariantResult:
    """Evaluate one metamorphic invariant against captured reference results."""
    return _HANDLERS[inv.kind](inv, results)
