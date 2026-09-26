# Discarded runs

Kept rather than deleted. A run thrown away for a known reason is evidence about
the harness; a run silently deleted is a gap in the record.

## `openai-contaminated-2026-09-26`

65 cells of a 108-cell `gpt-4.1` grid. **Discarded in full.**

The grid ran against the same Snowflake database that CI was applying chaos
variants to. Three pushes during the run each triggered a `warehouse` job, and
one of those runs was **cancelled** — which leaves a planted defect live, as the
code comment in `chaos()` had already warned.

One cell recorded **461,925,638.35** against a ground truth of **1,032,569.31**:
a 447× fan-out. The agent's SQL was correct. Re-running that exact statement
afterwards returned the right answer. The warehouse had been deliberately broken
underneath it and nothing noticed.

**It was nearly published as a finding about the model.** A number that extreme
looked like the fan-out trap firing under a new provider — the single result the
experiment most wanted to observe. Contamination that confirms your thesis is
the kind that gets written up.

Discarded entirely rather than partially, because the cards carried no
timestamps and no individual cell could be cleared. That gap is now closed:
every card records `_recorded_at`.

What changed as a result:

- `gtm_analyst/harness/integrity.py` — a canary checked before **every**
  question, not once at the start. Halts the run rather than warning, because a
  warning scrolls past and the remaining cells get recorded as though nothing
  happened.
- The canary set was chosen by **measurement**. The first version picked one
  question by reasoning about which joins it touched; applying all five chaos
  variants showed it caught one in five. The measured covering set catches 5/5,
  including a row-count fingerprint for the variant that keeps every value
  correct while dropping rows.
- Cards now carry `_recorded_at`, so a future contamination window can be
  scoped instead of forcing a full discard.

The operational lesson is duller and also true: do not push to a repository
whose CI mutates the warehouse an experiment is reading.
