"""Confirm the warehouse still matches frozen ground truth before trusting it.

A run that cannot trust its warehouse must stop rather than record numbers.

Not hypothetical. A 108-cell grid ran while CI was applying chaos variants to
the same Snowflake database, and one cell recorded 461,925,638.35 against a
ground truth of 1,032,569.31 -- a 447x fan-out. The agent's SQL was correct;
re-running it afterwards returned the right answer. The warehouse had been
deliberately broken underneath it and nothing noticed.

The dangerous part is what nearly happened next. A number that extreme looked
like the fan-out trap firing under a new model, which is precisely the result
the experiment was hoping to observe. Contamination that confirms your thesis is
the kind you publish.
"""
from collections.abc import Callable
from typing import Any

# Chosen by MEASUREMENT, not intuition. Each of the five chaos variants was
# applied in turn and every candidate question checked for whether it moved.
# A single question turned out to catch one variant in five -- the first version
# of this file picked q006 by reasoning about which joins it touched, and that
# reasoning was wrong.
#
# variant                  q001  q002  q006  q010  q011
# fanout_join              CATCH   -   CATCH   -   CATCH
# calendar_too_short         -     -     -     -     -
# wrong_effective_date       -     -     -     -   CATCH
# off_by_one_quarter       CATCH CATCH   -   CATCH CATCH
# coalesce_swallows_null     -     -     -   CATCH   -
#
# Minimal covering set, 4 of 5:
CANARY_QUESTIONS = (
    ("q001", "FINANCE_GLOBAL"),   # fan-out, shifted period boundary
    ("q010", "FINANCE_GLOBAL"),   # a grouping that lost its NULL segment
    ("q011", "FINANCE_GLOBAL"),   # effective-dated join window
)

# `calendar_too_short` moves NONE of them: it drops rows in the recognition tail
# beyond the quarter these questions ask about, so every answer stays correct
# while the warehouse is quietly smaller. A row-count fingerprint catches what
# value comparisons cannot.
CANARY_ROW_COUNTS = (
    ("FINANCE_GLOBAL", "V_REVENUE"),
    ("FINANCE_GLOBAL", "V_BOOKINGS"),
)

# Kept for the single-canary helpers and tests.
CANARY = CANARY_QUESTIONS[0]


class WarehouseChanged(RuntimeError):
    """Frozen ground truth no longer reproduces. The run must not continue."""


def verify_ground_truth(
    run: Callable[[], list[dict[str, Any]]],
    expected: list[dict[str, Any]],
) -> None:
    """Run the canary and halt if it no longer matches.

    Halt rather than warn. A warning scrolls past and the remaining cells get
    recorded as though nothing happened -- which is how a corrupted grid reaches
    a report looking complete.

    A query failure propagates untouched: being unable to check is not the same
    as having checked.
    """
    actual = run()
    if actual == expected:
        return
    raise WarehouseChanged(
        f"the warehouse no longer matches frozen ground truth for "
        f"{CANARY[0]}/{CANARY[1]}.\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}\n"
        f"Halting rather than recording numbers from a warehouse that changed "
        f"mid-run. The usual cause is something rebuilding models concurrently "
        f"-- a chaos run, a CI job, or a dbt build sharing this database. Do not "
        f"start by debugging the agent."
    )


def canary_checker(spec_root, spec) -> Callable[[], None]:
    """Build a no-argument integrity check against the live warehouse.

    Cheap: a handful of Snowflake queries and no model calls, so it can run
    before every question rather than once at the start. A single check at the
    top proves only that the warehouse was healthy before anything mattered.
    """
    from gtm_analyst.connection import session_for_persona
    from gtm_analyst.runner.reference import run_reference

    by_id = {q.id: q for q in spec.questions}
    cases = []
    for question_id, persona_name in CANARY_QUESTIONS:
        question = by_id[question_id]
        persona = spec.personas[persona_name]
        expected = next(e.rows for e in question.expected if e.persona == persona_name)
        cases.append((question, persona, expected))

    # Row counts are recorded on first call, so the fingerprint comes from the
    # warehouse as it stood when the run began rather than from a constant
    # somebody has to remember to update.
    baseline: dict[tuple[str, str], int] = {}

    def _count(persona_name: str, view: str) -> int:
        with session_for_persona(spec.personas[persona_name]) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {view}")
            return int(cursor.fetchone()[0])

    def check() -> None:
        for question, persona, expected in cases:
            verify_ground_truth(
                lambda q=question, p=persona: run_reference(spec_root, q, p).rows,
                expected,
            )
        for persona_name, view in CANARY_ROW_COUNTS:
            observed = _count(persona_name, view)
            key = (persona_name, view)
            if key not in baseline:
                baseline[key] = observed
            elif observed != baseline[key]:
                raise WarehouseChanged(
                    f"{view} went from {baseline[key]} to {observed} rows for "
                    f"{persona_name} mid-run. Values can stay correct while the "
                    f"warehouse quietly loses rows, so this is checked "
                    f"separately. Halting rather than recording numbers from a "
                    f"warehouse that changed; look for a concurrent chaos run, "
                    f"CI job, or dbt build rebuilt against this database."
                )

    return check
