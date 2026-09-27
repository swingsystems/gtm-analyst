# Experiment results

Reported under the schema fixed in `docs/adr/0003-three-arms-and-pre-registered-reporting.md` before any number existed. There is deliberately no single accuracy figure.

## Coverage and conditional accuracy

| arm | attempted | coverage | correct | conditional accuracy |
|---|---|---|---|---|
| free-sql | 36 | 36/36 | 14 | 39% |
| safe-join-contract | 19 | 19/36 | 14 | 74% |
| strict-contract | 23 | 23/36 | 12 | 52% |

**Coverage is not accuracy.** An arm that declines half the questions and is right about the rest has higher conditional accuracy and less use.

## Refusals, by kind

| arm | appropriate | capability | total |
|---|---|---|---|
| free-sql | 3 | 0 | 3 |
| safe-join-contract | 5 | 17 | 22 |
| strict-contract | 3 | 13 | 16 |

Declining an ambiguous question and being unable to express one are different things and are never summed.

## Head to head

Questions every arm could express: 4 (q001, q002, q007, q010)

| arm | correct | of | accuracy |
|---|---|---|---|
| free-sql | 11 | 12 | 92% |
| safe-join-contract | 12 | 12 | 100% |
| strict-contract | 12 | 12 | 100% |

The only like-for-like comparison in this document.

## Safety bonus

Questions the strict arm could not express: q003, q004, q006, q008, q011

| arm | wrong on those questions | of |
|---|---|---|
| free-sql | 13 | 15 |
| safe-join-contract | 3 | 15 |
| strict-contract | 2 | 15 |

The strict arm's inexpressibility is only a safety property if the other arms actually got these wrong. This is that number, and it is conditional.

## Failure categories

Denominators are questions where the category is testable for that arm, never the full set.

| arm | category | count |
|---|---|---|
| free-sql | fanout_double_count | 1 |
| free-sql | governance_over_block | 2 |
| free-sql | orphans_dropped | 1 |
| free-sql | unresolvable | 2 |
| free-sql | wrong_column | 15 |
| free-sql | wrong_join_grain | 1 |
| safe-join-contract | fanout_double_count | 3 |
| safe-join-contract | orphans_dropped | 2 |
| strict-contract | fanout_double_count | 4 |
| strict-contract | orphans_dropped | 4 |
| strict-contract | unresolvable | 2 |
| strict-contract | wrong_column | 1 |

## Every cell

| question | persona | arm | outcome | category | note |
|---|---|---|---|---|---|
| q001 | FINANCE_GLOBAL | free-sql | correct | — | total,shape,declared |
| q001 | FINANCE_GLOBAL | safe-join-contract | correct | — | total,shape,declared |
| q001 | FINANCE_GLOBAL | strict-contract | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | free-sql | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | safe-join-contract | correct | — | total,shape,declared |
| q001 | REP_INDIVIDUAL | strict-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | free-sql | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | safe-join-contract | correct | — | total,shape,declared |
| q001 | SALES_DIR_EMEA | strict-contract | correct | — | total,shape,declared |
| q002 | FINANCE_GLOBAL | free-sql | correct | — | total,shape,declared |
| q002 | FINANCE_GLOBAL | safe-join-contract | correct | — | total,shape,declared |
| q002 | FINANCE_GLOBAL | strict-contract | correct | — | total,shape,declared |
| q002 | REP_INDIVIDUAL | free-sql | correct | — | total,shape,declared |
| q002 | REP_INDIVIDUAL | safe-join-contract | correct | — | total,shape,declared |
| q002 | REP_INDIVIDUAL | strict-contract | correct | — | total,shape,declared |
| q002 | SALES_DIR_EMEA | free-sql | correct | — | total,shape,declared |
| q002 | SALES_DIR_EMEA | safe-join-contract | correct | — | total,shape,declared |
| q002 | SALES_DIR_EMEA | strict-contract | correct | — | total,shape,declared |
| q003 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape,declared |
| q003 | FINANCE_GLOBAL | safe-join-contract | wrong | fanout_double_count | declared |
| q003 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q003 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q003 | REP_INDIVIDUAL | safe-join-contract | wrong | fanout_double_count | declared |
| q003 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q003 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q003 | SALES_DIR_EMEA | safe-join-contract | wrong | fanout_double_count | declared |
| q003 | SALES_DIR_EMEA | strict-contract | wrong | fanout_double_count | declared |
| q004 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape,declared |
| q004 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q004 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q004 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q004 | REP_INDIVIDUAL | safe-join-contract | inexpressible | — | declared |
| q004 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q004 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q004 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q004 | SALES_DIR_EMEA | strict-contract | inexpressible | — | declared |
| q005 | FINANCE_GLOBAL | free-sql | wrong | orphans_dropped | declared |
| q005 | FINANCE_GLOBAL | safe-join-contract | wrong | orphans_dropped | declared |
| q005 | FINANCE_GLOBAL | strict-contract | wrong | orphans_dropped | declared |
| q005 | REP_INDIVIDUAL | free-sql | wrong | governance_over_block | declared |
| q005 | REP_INDIVIDUAL | safe-join-contract | wrong | orphans_dropped | declared |
| q005 | REP_INDIVIDUAL | strict-contract | wrong | orphans_dropped | declared |
| q005 | SALES_DIR_EMEA | free-sql | wrong | governance_over_block | declared |
| q005 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q005 | SALES_DIR_EMEA | strict-contract | wrong | orphans_dropped | declared |
| q006 | FINANCE_GLOBAL | free-sql | correct | — | total,shape |
| q006 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q006 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q006 | REP_INDIVIDUAL | free-sql | correct | — | total,shape,declared |
| q006 | REP_INDIVIDUAL | safe-join-contract | inexpressible | — | declared |
| q006 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q006 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q006 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q006 | SALES_DIR_EMEA | strict-contract | inexpressible | — | declared |
| q007 | FINANCE_GLOBAL | free-sql | correct | — | declared |
| q007 | FINANCE_GLOBAL | safe-join-contract | correct | — | declared |
| q007 | FINANCE_GLOBAL | strict-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | free-sql | correct | — | declared |
| q007 | REP_INDIVIDUAL | safe-join-contract | correct | — | declared |
| q007 | REP_INDIVIDUAL | strict-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | free-sql | correct | — | declared |
| q007 | SALES_DIR_EMEA | safe-join-contract | correct | — | declared |
| q007 | SALES_DIR_EMEA | strict-contract | correct | — | declared |
| q008 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape,declared |
| q008 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q008 | FINANCE_GLOBAL | strict-contract | inexpressible | — | declared |
| q008 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q008 | REP_INDIVIDUAL | safe-join-contract | inexpressible | — | declared |
| q008 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q008 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q008 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q008 | SALES_DIR_EMEA | strict-contract | inexpressible | — | declared |
| q009 | FINANCE_GLOBAL | free-sql | correct | — | total,shape,declared |
| q009 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q009 | FINANCE_GLOBAL | strict-contract | wrong | fanout_double_count | declared |
| q009 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q009 | REP_INDIVIDUAL | safe-join-contract | inexpressible | — | declared |
| q009 | REP_INDIVIDUAL | strict-contract | wrong | fanout_double_count | declared |
| q009 | SALES_DIR_EMEA | free-sql | wrong | wrong_column | shape,declared |
| q009 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q009 | SALES_DIR_EMEA | strict-contract | wrong | fanout_double_count | declared |
| q010 | FINANCE_GLOBAL | free-sql | correct | — | total,shape,declared |
| q010 | FINANCE_GLOBAL | safe-join-contract | correct | — | total,shape,declared |
| q010 | FINANCE_GLOBAL | strict-contract | correct | — | total,shape,declared |
| q010 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q010 | REP_INDIVIDUAL | safe-join-contract | correct | — | total,shape,declared |
| q010 | REP_INDIVIDUAL | strict-contract | correct | — | total,shape,declared |
| q010 | SALES_DIR_EMEA | free-sql | correct | — | total,shape,declared |
| q010 | SALES_DIR_EMEA | safe-join-contract | correct | — | total,shape,declared |
| q010 | SALES_DIR_EMEA | strict-contract | correct | — | total,shape,declared |
| q011 | FINANCE_GLOBAL | free-sql | wrong | wrong_join_grain | total,declared |
| q011 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q011 | FINANCE_GLOBAL | strict-contract | wrong | orphans_dropped | declared |
| q011 | REP_INDIVIDUAL | free-sql | wrong | wrong_column | shape,declared |
| q011 | REP_INDIVIDUAL | safe-join-contract | inexpressible | — | declared |
| q011 | REP_INDIVIDUAL | strict-contract | inexpressible | — | declared |
| q011 | SALES_DIR_EMEA | free-sql | wrong | fanout_double_count | declared |
| q011 | SALES_DIR_EMEA | safe-join-contract | inexpressible | — | declared |
| q011 | SALES_DIR_EMEA | strict-contract | inexpressible | — | declared |
| q012 | FINANCE_GLOBAL | free-sql | wrong | wrong_column | shape,declared |
| q012 | FINANCE_GLOBAL | safe-join-contract | inexpressible | — | declared |
| q012 | FINANCE_GLOBAL | strict-contract | wrong | wrong_column | superset,declared |
| q012 | REP_INDIVIDUAL | free-sql | wrong | unresolvable | declared |
| q012 | REP_INDIVIDUAL | safe-join-contract | correct | — | declared |
| q012 | REP_INDIVIDUAL | strict-contract | wrong | unresolvable | declared |
| q012 | SALES_DIR_EMEA | free-sql | wrong | unresolvable | declared |
| q012 | SALES_DIR_EMEA | safe-join-contract | correct | — | declared |
| q012 | SALES_DIR_EMEA | strict-contract | wrong | unresolvable | declared |
