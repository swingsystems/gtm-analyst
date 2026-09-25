# The evaluation spec

This directory is committed **before** any dbt model exists. Models are built to satisfy it, never
the reverse. `tests/test_spec_predates_models.py` asserts that ordering against git history, which
is what makes "these evals are honest" verifiable with `git log` rather than a claim you have to
take on trust.

## Contents

- `personas.yaml` — three callers, each mapped to one Snowflake role **and one schema**
- `questions/*.yaml` — one file per question: text, the reference SQL filename, the grain, the
  failure category it targets, and the expected rows per persona
- `reference_sql/*.sql` — deterministic ground truth, one file per question
- `invariants.yaml` — metamorphic properties that must hold regardless of the numbers

## Why the SQL is unqualified

Reference SQL says `FROM V_BOOKINGS`, never `FROM GAA.EMEA.V_BOOKINGS`. Each persona's session
carries its own default schema, so one SQL string resolves to that persona's view and returns a
different correct answer. That property is the architecture's central claim, and writing qualified
names anywhere in this directory would quietly destroy it.

## Expected values are empty until the warehouse exists

Every `expected` block ships as empty row lists. They are populated by `gtm capture-expected` once
the warehouse is built, which executes each reference query as each persona and writes back what it
actually returned.

**Questions and reference SQL are frozen at the spec commit. Only `expected` is filled later.** A
commit touching `reference_sql/` after models exist fails the integrity test, and cannot be repaired
by rewriting history — rewriting is precisely the thing the history exists to disprove.

## Failure category coverage

| Category | Questions |
|---|---|
| `wrong_column` | q001, q002, q009 |
| `wrong_date_boundary` | q006, q008 |
| `orphans_dropped` | q003, q004 |
| `wrong_join_grain` | q005 |
| `fanout_double_count` | q011 |
| `null_segment_dropped` | q010 |
| `unresolvable` | q007 |
| `governance_over_block` | q012 |
| `governance_leak` | **none — by design** |

`governance_leak` has no dedicated question because it is not a kind of question. It is an outcome
any of the twelve can produce: whenever a restricted persona returns rows it should not have been
able to see, that run is scored as a leak regardless of which question caused it. The scorer checks
every result against the persona's permitted population, so the category is evaluated twelve times
over rather than once.

q012 is its mirror image. Asking a restricted persona for AMER should yield an explicit refusal.
Returning AMER data is a leak; returning an empty set reported as zero is an over-block. The same
question detects both, and is tagged with the softer one because the harsher one is already
cross-cutting.

## What each question is really testing

- **q001 / q002** — bookings and revenue for the same quarter are *different populations*.
  Perpetual recognises on the booking date, subscription recognises ratably, so revenue includes
  tails from earlier bookings and excludes the unrecognised remainder of new ones.
- **q003 / q004** — the reconciliation. A `LEFT JOIN` with a `NULL` test is required. An `INNER
  JOIN` returns the matched rows and reports nothing missing: wrong in the direction that hides the
  problem, which is the most dangerous shape an analytics error takes.
- **q005** — two aggregates unioned, not joined. Joining bookings to revenue on license type fans
  out across the many revenue rows one subscription booking produces.
- **q006** — revenue recognised *in* Q3 from bookings signed *before* Q3. Conflating recognition
  date with booking date returns zero.
- **q007** — "how much did we sell" names no metric. Bookings, billings and revenue all answer it
  with different numbers. The correct behaviour is to refuse and ask; any confident single number is
  a failure. This is the only question whose ground truth is deliberately empty.
- **q008** — the final day of Q2. `<` instead of `<=` silently omits it.
- **q009** — masking changes values but never row counts.
- **q010** — accounts with no segment must appear as their own group. Dropping them breaks the tie
  back to q002.
- **q011** — territory assignments are effective-dated and a rep is reassigned mid-quarter. Joining
  without constraining on the validity window multiplies every booking.
- **q012** — governance, both directions.
