# Deliberately broken model variants

Each file replaces one dbt model with a version carrying a known defect. The
harness must catch every one; CI requires a 100% catch rate.

An evaluation suite that has never been seen to fail is not evidence. These
exist so the catch rate is a measured number rather than an assumption — and
because this project has already shipped one of these bugs for real.

## Built and exercised in CI

| Variant | Defect | Caught by |
|---|---|---|
| `calendar_too_short` | fiscal calendar ends before the longest recognition schedule | `assert_no_rows_lost_revenue`, and every revenue question |
| `coalesce_swallows_null` | staging replaces a NULL segment with a literal, so the null group vanishes | q010 |

**Catch rate: 2 of 2.** That denominator is what exists, not what was planned.

## Planned, NOT built

Listed so the coverage gap is visible rather than implied away. A table that
reads as complete coverage when three of five variants do not exist is the same
failure as an eval reporting accuracy over only the questions it could attempt.

| Variant | Defect | Would be caught by |
|---|---|---|
| `fanout_join` | `fct_bookings` joins the calendar without a date equality, multiplying rows | totals inflate across every bookings question |
| `wrong_effective_date` | territory validity window read inclusively instead of half-open | q011 |
| `off_by_one_quarter` | quarter boundary shifted by a day | q008 |

`calendar_too_short` is not hypothetical. It was committed for real in `e517ed4`
and silently discarded 1,159 revenue rows while dbt reported success. The suite
has to catch a mistake this project has already made once.
