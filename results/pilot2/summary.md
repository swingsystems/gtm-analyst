# Experiment results — PARTIAL PILOT

**25 of 36 cells.** The run stopped when the Anthropic account reached its usage
limit, part-way through q011. All of q012 is missing, along with two q011 cells.
The tables below are over what ran, not over what was planned.

**Four questions, not twelve.** This is a pilot slice chosen to exercise the
interesting cases — a plain question, an ambiguous one, the fan-out trap, and a
governance refusal — not the full evaluation set.

**One run per cell.** No repeats. A separate q011 trial run four times produced
row counts of 3, 68, 13 and 68 for an identical question, so single-run cells
carry more variance than these tables can show.

Read the head-to-head as n=2 questions, six cells per arm. One flipped cell moves
an arm by seventeen points.

Reported under the schema fixed in `docs/adr/0003-three-arms-and-pre-registered-reporting.md` before any number existed. There is deliberately no single accuracy figure.

## Coverage and conditional accuracy

| arm | attempted | coverage | correct | conditional accuracy |
|---|---|---|---|---|
| free-sql | 9 | 9/9 | 5 | 56% |
| safe-join-contract | 8 | 8/8 | 6 | 75% |
| strict-contract | 6 | 6/8 | 6 | 100% |

**Coverage is not accuracy.** An arm that declines half the questions and is right about the rest has higher conditional accuracy and less use.

## Refusals, by kind

| arm | appropriate | capability | total |
|---|---|---|---|
| free-sql | 3 | 0 | 3 |
| safe-join-contract | 3 | 0 | 3 |
| strict-contract | 3 | 2 | 5 |

Declining an ambiguous question and being unable to express one are different things and are never summed.

## Head to head

Questions every arm could express: 2 (q001, q007)

| arm | correct | of | accuracy |
|---|---|---|---|
| free-sql | 5 | 6 | 83% |
| safe-join-contract | 6 | 6 | 100% |
| strict-contract | 6 | 6 | 100% |

The only like-for-like comparison in this document.

## Safety bonus

Questions the strict arm could not express: q011

| arm | wrong on those questions | of |
|---|---|---|
| free-sql | 3 | 3 |
| safe-join-contract | 2 | 2 |
| strict-contract | 0 | 2 |

The strict arm's inexpressibility is only a safety property if the other arms actually got these wrong. This is that number, and it is conditional.

## Failure categories

Denominators are questions where the category is testable for that arm, never the full set.

| arm | category | count |
|---|---|---|
| free-sql | fanout_double_count | 1 |
| free-sql | orphans_dropped | 1 |
| free-sql | wrong_column | 1 |
| free-sql | wrong_join_grain | 1 |
| safe-join-contract | wrong_column | 1 |
| safe-join-contract | wrong_join_grain | 1 |

## Every cell

| question | persona | arm | outcome | category | note |
|---|---|---|---|---|---|
| q001 | FINANCE_GLOBAL | free-sql | correct | — | total,shape |
| q001 | FINANCE_GLOBAL | safe-join-contract | correct | — | total,shape |
| q001 | FINANCE_GLOBAL | strict-contract | correct | — | total,shape |
| q001 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q001 | REP_INDIVIDUAL | safe-join-contract | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | strict-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | free-sql | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | safe-join-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | strict-contract | correct | — | total,shape,declared |
| q007 | FINANCE_GLOBAL | free-sql | correct | — | declared |
| q007 | FINANCE_GLOBAL | safe-join-contract | correct | — | declared |
| q007 | FINANCE_GLOBAL | strict-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | free-sql | correct | — | declared |
| q007 | REP_INDIVIDUAL | safe-join-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | strict-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | free-sql | correct | — | declared |
| q007 | SALES_DIR_EMEA | safe-join-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | strict-contract | correct | — | declared |
| q011 | FINANCE_GLOBAL | free-sql | wrong | orphans_dropped | declared |
| q011 | FINANCE_GLOBAL | safe-join-contract | wrong | wrong_join_grain | total |
| q011 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q011 | REP_INDIVIDUAL | free-sql | wrong | wrong_join_grain | total,declared |
| q011 | SALES_DIR_EMEA | free-sql | wrong | fanout_double_count | declared |
| q011 | SALES_DIR_EMEA | safe-join-contract | wrong | wrong_column | shape,declared |
| q011 | SALES_DIR_EMEA | strict-contract | inexpressible | — | declared |
