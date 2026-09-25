# Pointing this at your own models

The reference warehouse exists so the architecture runs end to end out of the
box. It is meant to be replaced. Nothing above it knows or cares that the data
is synthetic.

## What actually has to change

**1. Your dbt models replace `warehouse/models/`.** No constraint on how you
model, with two exceptions that are not stylistic:

- **Money is `NUMBER(38,2)`, never `FLOAT`.** Rounding artifacts are
  indistinguishable from real metric errors, and the evaluation cannot tell them
  apart either.
- **One table owns period boundaries.** Here it is `dim_fiscal_calendar`. If
  quarter logic is scattered across models, an off-by-one appears in some
  answers and not others and you will chase it for a week.

**2. Persona views.** One schema per persona, holding **identically named**
views. This is the mechanism, not a convention: reference SQL is unqualified, so
the session's default schema is what makes one query return a different correct
answer per identity.

```
GAA.FINANCE.V_BOOKINGS   -- unfiltered
GAA.EMEA.V_BOOKINGS      -- WHERE REGION = 'EMEA'
GAA.REP.V_BOOKINGS       -- WHERE OWNER_REP_ID = ...
```

Denormalise the columns your views filter on into the facts. A join inside a
secure view is another surface where a filter can be forgotten.

**3. Metric contracts** in `semantic/contracts/`, one YAML per metric. Declare
the column and aggregation, the dimensions it may be sliced by, the filters that
apply whether or not the caller asks, and whether nulls survive aggregation.

Write real descriptions. The agent reads them through `describe_metric`, and a
thin description produces a worse answer for reasons that have nothing to do
with your data. One of ours was 38 characters and it mattered.

**4. Your questions and reference SQL.** Take the questions your finance and
sales teams actually argue about. For each, write the SQL you are confident in.

**Commit these before you build the models they evaluate.** That ordering is the
only thing separating an honest evaluation from one tuned to pass, and
`tests/test_spec_predates_models.py` asserts it from git history. It is worth the
discipline: ground truth here was wrong three times, and each time the frozen
spec forced the *data* to be fixed rather than the expectation quietly lowered.

## What you get for it

`make eval` reports per-category failure rates. Not one accuracy number —
categories have different causes and different fixes, and an aggregate hides the
one getting worse.

`gaa check-invariants` runs metamorphic properties: global equals the sum of
regions, rep ≤ region ≤ global, masking changes values but never row counts.
These catch a **wrong oracle**, which matters because you wrote the oracle.

The chaos suite plants known defects and requires the harness to catch them. A
suite that has never been seen to fail is not evidence.

## Where it will fight you

**Definitional divergence, and expect a lot of it.** The commonest disagreement
between agent and reference here was not arithmetic — the agent applied a
default the contract declared and the reference SQL did not. Those are arguments
about what a metric means, surfaced by the harness. Budget time for them; they
are the valuable output of the first month, not a defect.

**Questions no contract can express.** Cross-fact set differences, effective-dated
joins, anything needing a join the contracts do not declare. The strict arm
returns "inexpressible", which is a third outcome and never counted as an error.
If most of your questions land there, your contracts are too narrow — or the
question genuinely needs SQL, which is also a finding.

**Standard Edition.** Row access policies and masking policies are Enterprise.
This architecture works on Standard using schema-scoped grants, which is why it
deploys anywhere — but the boundary rests on grants being right rather than on a
policy attached to the table. A mis-grant exposes a schema. Test grants
adversarially; `tests/test_governance_boundary.py` shows how.
