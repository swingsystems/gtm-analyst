# Experiment results

Reported under the schema fixed in `docs/adr/0003-three-arms-and-pre-registered-reporting.md` before any number existed. There is deliberately no single accuracy figure.

## Coverage and conditional accuracy

| arm | attempted | coverage | correct | conditional accuracy |
|---|---|---|---|---|
| free-sql | 12 | 12/12 | 3 | 25% |
| safe-join-contract | 12 | 12/12 | 6 | 50% |
| strict-contract | 10 | 10/12 | 6 | 60% |

**Coverage is not accuracy.** An arm that declines half the questions and is right about the rest has higher conditional accuracy and less use.

## Refusals, by kind

| arm | appropriate | capability | total |
|---|---|---|---|
| free-sql | 2 | 0 | 2 |
| safe-join-contract | 3 | 0 | 3 |
| strict-contract | 3 | 2 | 5 |

Declining an ambiguous question and being unable to express one are different things and are never summed.

## Head to head

Questions every arm could express: 3 (q001, q007, q012)

| arm | correct | of | accuracy |
|---|---|---|---|
| free-sql | 3 | 9 | 33% |
| safe-join-contract | 6 | 9 | 67% |
| strict-contract | 6 | 9 | 67% |

The only like-for-like comparison in this document.

## Safety bonus

Questions the strict arm could not express: q011

| arm | wrong on those questions | of |
|---|---|---|
| free-sql | 3 | 3 |
| safe-join-contract | 3 | 3 |
| strict-contract | 1 | 3 |

The strict arm's inexpressibility is only a safety property if the other arms actually got these wrong. This is that number, and it is conditional.

## Failure categories

Denominators are questions where the category is testable for that arm, never the full set.

| arm | category | count |
|---|---|---|
| free-sql | orphans_dropped | 3 |
| free-sql | unresolvable | 3 |
| free-sql | wrong_column | 3 |
| safe-join-contract | unresolvable | 2 |
| safe-join-contract | wrong_column | 3 |
| safe-join-contract | wrong_join_grain | 1 |
| strict-contract | fanout_double_count | 1 |
| strict-contract | unresolvable | 2 |
| strict-contract | wrong_column | 1 |

## Every cell

| question | persona | arm | outcome | category | note |
|---|---|---|---|---|---|
| q001 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape |
| q001 | FINANCE_GLOBAL | safe-join-contract | correct | — | total,shape |
| q001 | FINANCE_GLOBAL | strict-contract | correct | — | total,shape |
| q001 | REP_INDIVIDUAL | free-sql | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | safe-join-contract | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | strict-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q001 | SALES_DIR_EMEA | safe-join-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | strict-contract | correct | — | total,shape |
| q007 | FINANCE_GLOBAL | free-sql | correct | — | declared |
| q007 | FINANCE_GLOBAL | safe-join-contract | correct | — | declared |
| q007 | FINANCE_GLOBAL | strict-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | free-sql | wrong | unresolvable | declared |
| q007 | REP_INDIVIDUAL | safe-join-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | strict-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | free-sql | correct | — | declared |
| q007 | SALES_DIR_EMEA | safe-join-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | strict-contract | correct | — | declared |
| q011 | FINANCE_GLOBAL | free-sql | wrong | orphans_dropped | — |
| q011 | FINANCE_GLOBAL | safe-join-contract | wrong | wrong_join_grain | total,declared |
| q011 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q011 | REP_INDIVIDUAL | free-sql | wrong | orphans_dropped | declared |
| q011 | REP_INDIVIDUAL | safe-join-contract | wrong | wrong_column | shape,declared |
| q011 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q011 | SALES_DIR_EMEA | free-sql | wrong | orphans_dropped | — |
| q011 | SALES_DIR_EMEA | safe-join-contract | wrong | wrong_column | shape,declared |
| q011 | SALES_DIR_EMEA | strict-contract | wrong | fanout_double_count | declared |
| q012 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape,declared |
| q012 | FINANCE_GLOBAL | safe-join-contract | wrong | wrong_column | superset |
| q012 | FINANCE_GLOBAL | strict-contract | wrong | wrong_column | superset |
| q012 | REP_INDIVIDUAL | free-sql | wrong | unresolvable | declared |
| q012 | REP_INDIVIDUAL | safe-join-contract | wrong | unresolvable | declared |
| q012 | REP_INDIVIDUAL | strict-contract | wrong | unresolvable | declared |
| q012 | SALES_DIR_EMEA | free-sql | wrong | unresolvable | declared |
| q012 | SALES_DIR_EMEA | safe-join-contract | wrong | unresolvable | declared |
| q012 | SALES_DIR_EMEA | strict-contract | wrong | unresolvable | declared |
