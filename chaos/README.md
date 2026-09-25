# Deliberately broken model variants

Each file replaces one dbt model with a version carrying a known defect. The
harness must catch every one.

**These do not run in CI.** Each variant rebuilds models against a live
Snowflake account, and CI holds no credentials, so 7 of the 8 chaos tests skip
there. The catch rate below was measured locally on 2026-09-25 and is a
point-in-time measurement, not a gate. Wiring it to a CI warehouse is listed in
the README as outstanding.

An evaluation suite that has never been seen to fail is not evidence. These
exist so the catch rate is a measured number rather than an assumption — and
because this project has already shipped two of these bugs for real.

## Built and exercised (locally, against a live account)

| Variant | Defect | Caught by |
|---|---|---|
| `calendar_too_short` | fiscal calendar ends before the longest recognition schedule | `assert_no_rows_lost_revenue`, and every revenue question |
| `coalesce_swallows_null` | staging replaces a NULL segment with a literal, so the null group vanishes | q010 |
| `fanout_join` | `fct_bookings` joins the calendar on year alone, dropping the date equality | the `unique` test on `BOOKING_ID`, before any question is asked |
| `wrong_effective_date` | `VALID_TO` pushed out a day, so the window is inclusive where consumers read it half-open | q011 |
| `off_by_one_quarter` | every date labelled with the following day's quarter | **q001**, not q008 — see below |

**Catch rate: 5 of 5**, measured by `test_the_catch_rate_is_total` against the
live warehouse.

Two of the five are not hypothetical:

- `calendar_too_short` was committed for real in `e517ed4` and silently
  discarded 1,159 revenue rows while dbt reported success.
- `wrong_effective_date` is the mirror image of a real defect here: the
  generator wrote inclusive end dates while the reference SQL read them
  half-open, losing 180,848.13 at handovers. It was found because the free-SQL
  agent refused to answer and kept probing instead.

## One prediction was wrong, and it is kept rather than corrected away

This file previously listed `off_by_one_quarter` as caught by **q008**. That was
written before the variant existed, and it was wrong.

q008 asks which bookings landed on the last day of Q2 and filters on
`BOOKING_DATE`. It never reads `FISCAL_QUARTER`, so shifting every quarter label
leaves q008 perfectly correct. q001 filters on `FISCAL_QUARTER` and moves.

`test_off_by_one_quarter_is_caught_but_not_by_the_question_predicted` asserts
**both** halves: that q008 stays blind, and that q001 catches it. It is worth a
test rather than a footnote, because the planted defect and the detector meant
to catch it were chosen by the same person on the same day — and one of them was
wrong. That is the failure mode this whole directory exists to expose, and it
showed up in the directory itself.

## Adding a variant

1. Write the broken model in `chaos/<name>.sql`.
2. Register it in `gaa/harness/chaos.py` with its target, rebuild selector, and
   what should catch it.
3. Add a test that plants it, asserts the catch, and asserts the revert.
4. Run it. **If the detector you predicted does not fire, say so** rather than
   retargeting silently — an unfired prediction is information about the eval
   suite, not a bookkeeping detail.
