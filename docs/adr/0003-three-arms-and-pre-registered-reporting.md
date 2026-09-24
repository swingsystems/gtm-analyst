# ADR 0003 — Three arms, and the reporting schema, pre-registered

Date: 2026-09-24
Status: Accepted — **committed before the experiment runs**

This document fixes how the experiment will be reported *before* any result exists. Designing the
reporting framework after seeing the numbers makes the result unrecoverable however clean it looks,
so the ordering is load-bearing in the same way the spec-before-models ordering is. `git log` shows
this landed before `gaa/harness/run.py`.

## Context

The constrained agent can express only 4 of the 12 evaluation questions. The metric contracts have
no join surface, deliberately: joins inside a security boundary are where filters get forgotten.

Four options were considered. A cross-vendor review was unanimous against the one initially
preferred — denormalising `TERRITORY_ID` so all twelve become expressible.

**q011 is the fan-out trap.** Territory assignments are effective-dated and every rep is reassigned
mid-quarter, so joining without constraining on the validity window multiplies every booking.
Denormalise the territory onto the booking row and there is no join to mis-filter, no trap, and
nothing to discriminate on — for *either* arm. The free-SQL arm, which the trap exists to catch,
would simply select a column. One panelist: *"this is testing a seatbelt in a car that never
moves."* The headline would collapse to both arms scoring near-identically, which is a negative
result wearing a positive result's clothes.

## Decision

### Three arms, not two

| Arm | Description |
|---|---|
| **free-sql** | Agent writes arbitrary SELECT against the persona's views. No guardrails beyond the warehouse boundary. |
| **strict-contract** | Agent restricted to metric contracts with no join surface. Cannot express cross-fact questions. |
| **safe-join-contract** | Contracts may declare joins, but only with **mandatory predicates**. The compiler refuses to assemble SQL unless every mandatory predicate is present and parameter-bound. |

The third arm is what makes q011 discriminating rather than dodged. It tests the question the
architecture should actually be answering — *do declarative join contracts prevent the failure?* —
rather than *what happens if joins are forbidden entirely*, which is a less interesting question
with a more obvious answer.

On q011 specifically:

- **free-sql** may fall into `fanout_double_count`
- **strict-contract** returns `inexpressible`
- **safe-join-contract** passes when it includes the mandatory validity-window predicate, and
  fails with a *compiler error* — not a wrong number — when it omits it

### Expressibility fixes that do not destroy a trap

Applied: reconciliation views for the set-difference questions (q003, q004); `SEGMENT` and
`ACCOUNT_NAME` denormalised into the revenue fact, exactly as `REGION`, `OWNER_REP_ID` and
`LICENSE_TYPE` already are (q009, q010); q008 needed no change, an earlier analysis mislabelled a
filter as a dimension.

Not applied: `TERRITORY_ID` stays un-denormalised.

## The pre-registered reporting schema

**A single aggregate accuracy number will not be published.** The most likely way this experiment
produces a technically correct and substantively misleading result is reporting the constrained
arm's error rate over only the questions it could attempt, beside the free arm's rate over all
twelve. A reader averages those into "constrained is safer" and the paper reads correctly while
concluding wrongly.

Every result table reports, per arm:

1. **Coverage** — `(correct + wrong) / 12`. How many questions the arm could attempt at all.
2. **Conditional accuracy** — `correct / (correct + wrong)`. Accuracy given it answered.
3. **Refusals, split by kind** — *appropriate* (q007 ambiguity, q012 governance) versus *capability*
   (cannot express). These are not the same thing and will never be summed.
4. **Head-to-head** — accuracy on the subset expressible by **all three** arms. The only fair
   like-for-like comparison.
5. **Safety bonus** — for questions the strict arm could not express, how often the free-SQL arm was
   *wrong*. This is the conditional safety claim, and it is conditional.
6. **Per-category rates with explicit denominators.** `fanout_double_count` has denominator 1 for an
   arm that can attempt q011, not 12.

Per-question outcomes are published as a three-cell table — `correct | wrong | inexpressible` — with
no "n/a" and no "skipped", so the asymmetry is visible at row level rather than buried in an
aggregate.

## The q011 conditional, committed in advance

The strict arm's inexpressibility is only a safety property if the free arm actually commits the
failure it is protected from. That is falsifiable, and both branches are committed to now:

- **If free-sql falls into `fanout_double_count` on q011** — the strict arm's refusal is a
  structural safety win and is published as such, with the failure-mode asymmetry as evidence.
- **If free-sql answers q011 correctly** — the refusal bought nothing. The framing shifts to
  "capability tradeoff with no demonstrated safety benefit," and that is published with equal
  prominence.

Either way the safe-join arm's behaviour on q011 is reported separately, since it is the arm
designed to answer the question rather than avoid it.

## Scope of the claim

The finding is about **metric contracts as a design**, not semantic layers as a category. The
distinguishing test, taken from the review: would a practitioner reading the q009 contract say
"yes, that is how I would write this in dbt Semantic Layer, Cube, or LookML"? If yes, the result
generalises to metric contracts as commonly designed. If they would say "no, I would obviously model
account as a dimension with a join," the contracts are toy-shaped and the result is about toys.

The README will state the narrower claim. Asserting the broader one would require implementing the
same twelve questions in an existing semantic layer and comparing — which is not in scope and is
recorded here as the work that claim would need.

## Consequences

The experiment gets meaningfully larger: three arms across twelve questions and three personas is
108 cells rather than 72. The safe-join compiler is genuinely more work than the strict one, since
mandatory predicates have to be enforced at assembly time rather than documented.

Accepted, because the two-arm version answers a question nobody is really asking. "Forbidding joins
prevents join errors" is true and uninteresting. "Declarative join contracts with compiler-enforced
predicates prevent join errors while remaining expressive" is the claim worth testing, and it needs
the third arm to test it.
