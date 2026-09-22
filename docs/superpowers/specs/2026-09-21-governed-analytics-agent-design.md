# Reference Architecture — Governed Analytics Agents on Snowflake

Date: 2026-09-21
Status: Draft for review
Working name: `governed-analytics-agent`

## What this is

A deployable reference architecture for running analytics agents against governed enterprise data on
Snowflake, with the evaluation methodology that proves the agents are correct.

It is not a demo and not a portfolio exercise. It is an artifact another data organization clones,
deploys into their own Snowflake account, points at their own models, and adopts — with the patterns,
decision records, and conformance tests that make adoption safe.

**Provenance, stated plainly and kept accurate throughout:** built on a personal Snowflake account
against synthetic GTM data. The architecture, governance objects, agent, and evaluation harness are
real and independently reproducible. The data is not a real company's. Any reader can verify every
claim by deploying it themselves, which is the point — the credibility comes from reproducibility,
not from assertion.

## The problem it solves

Every vendor now asserts that grounding an LLM in a governed semantic layer makes analytics agents
trustworthy. Nobody has published the architecture for doing it safely, and nobody has published
evidence that it works.

Enterprise data teams face three unanswered questions when they try:

1. **Correctness** — does the agent return the right number, and how would you know?
2. **Governance** — when a sales rep and a CFO ask the same question, does the agent respect row
   access policies, or does it leak?
3. **Auditability** — when the agent produces a number that reaches a board deck, can you
   reconstruct how it got there?

This architecture answers all three with running code and a measured result.

## Design principles

1. **The agent's access surface is the governance boundary.** Not the prompt. Not a policy document.
   Enforcement lives in one layer, testable in isolation.
2. **Every answer is auditable by construction.** An answer without its SQL, metric versions,
   lineage, and policy context is not a deliverable.
3. **Governance refusal is a first-class result.** "I can't see AMER" beats a silently smaller
   number.
4. **The evaluation is adversarial toward its own author.** Mechanisms that could certify the
   author's own mistakes are treated as defects to be engineered out.
5. **Deployable by a stranger in one command, teardownable in one.** An architecture nobody can run
   is a diagram.

## Architecture

Five layers. Each is independently testable, independently replaceable, and documented as a pattern
adopters can map onto their own stack.

### 1. Warehouse (`warehouse/`)

A GTM/revenue domain: accounts, opportunities, bookings, ARR roll-forward, effective-dated quota and
territory assignment, fiscal calendar. dbt models, staged → intermediate → marts.

Adopters replace this layer entirely with their own models. It exists so the rest of the
architecture has something realistic to stand on, and so the reference deployment runs end to end
out of the box.

Non-negotiables, because they are the difference between a reference architecture and a toy:

- Monetary columns are `NUMBER(38,2)`. Never `FLOAT`. Rounding artifacts are indistinguishable from
  real metric errors and would corrupt the evaluation.
- Source timestamps in UTC; a fiscal calendar dimension owns every period boundary. No date
  arithmetic scattered through models.
- Territory and quota assignments are slowly-changing with effective dates. This is where real
  analytics agents fail — they apply today's territory to last quarter's bookings.
- NULL semantics declared per column in the contract, because a silently dropped NULL segment is a
  scored failure category.

### 2. Governance (`warehouse/governance/`)

Snowflake-native: RBAC role hierarchy, row access policies, masking policies, secure views. Three
reference personas:

| Persona | Sees | Analogue |
|---|---|---|
| `FINANCE_GLOBAL` | all territories | corporate FP&A |
| `SALES_DIR_EMEA` | EMEA only | regional sales leadership |
| `REP_INDIVIDUAL` | own accounts only | individual contributor |

The personas are not there to demonstrate that row access policies filter rows — any Snowflake
engineer knows that. They exist to generate **leak tests**. The architecture's claim is that an
*agent* cannot get around the policy, and the conformance suite asserts it against every bypass path:
role switching, default-role leakage, ownership chaining, querying unprotected base tables instead of
secure views, and inferring restricted values from aggregates.

### 3. Semantic layer (`semantic/`)

Versioned metric contracts in YAML, one per metric: name, description, owner, grain, measure
expression, permitted dimensions, default filters, NULL policy, fiscal-period binding, semantic
version.

This YAML is the single source for both the Snowflake semantic views and the MCP tool surface, so
the agent cannot drift from the contract.

Phase 2 opens with a verification step: confirm semantic view and Cortex Analyst availability for the
target account's edition and region. If unavailable, contracts compile to secure views instead; the
tool surface and the evaluation are unaffected. The architecture does not depend on that feature.

### 4. MCP server (`mcp_server/`)

The agent's entire access surface, and the layer adopters care most about.

- `list_metrics()` — discovery
- `describe_metric(name)` — contract, grain, dimensions, NULL policy
- `query_metric(name, dimensions, filters, period)` — governed, parameterized
- `run_sql(statement)` — read-only, policy-enforced; the unconstrained comparison arm
- `explain_lineage(name)` — objects touched, model versions

Rules: no string concatenation into SQL anywhere; the server holds no elevated role and executes
strictly as the caller's persona; every call logged with persona, role, policies in effect, and model
version. This is where the architecture's safety claim lives, so it carries the strictest tests.

### 5. Agent (`agent/`)

Python, Claude Agent SDK. Takes a natural-language question and a persona; plans, resolves to metrics
and dimensions, calls tools, returns an **answer card**:

```
answer:        the number(s)
sql:           exact statement executed
metrics_used:  name@version
lineage:       objects touched
context:       persona, role, policies in effect
confidence:    with stated basis
why_not:       populated when governance blocked part of the question
query_id:      Snowflake query ID, reconcilable against ACCOUNT_USAGE
```

The `query_id` matters for adoption: every answer is traceable to a row in Snowflake's own query
history, so an adopting organization can audit agent behaviour with tooling they already run.

## Evaluation methodology

The methodology is part of the architecture, not a test folder. An adopting team gets a way to
evaluate *their* agents against *their* models.

### Spec-first ordering

The evaluation spec — questions and deterministic reference SQL — is written and committed **before**
any dbt model exists. Models are then built to satisfy it. The ordering is visible in git history,
which converts "these evals are honest" from an assertion into something a skeptic verifies with
`git log`.

This addresses specification circularity: deterministic SQL removes label noise, but when one author
writes the models, the questions, *and* the reference queries, the evaluation can certify a wrong
metric definition as ground truth. Spec-first ordering plus the three mechanisms below is a
mitigation, not a cure, and the documentation says so.

### Ground truth

Each question carries deterministic reference SQL written against base tables, independent of the
semantic layer, with expected results per persona. Reference queries are minimal, assert their grain
explicitly, and recompile against current model artifacts on every CI run so ground truth cannot go
stale.

### Metamorphic invariants

Properties that hold regardless of the numbers, which catch a wrong oracle:

- `global == sum(regions)` for additive measures
- `rep ≤ region ≤ global` for any filtered measure
- masking changes distinct values, never row counts
- period sums reconcile to the annual roll-forward
- identical questions return identical results

### Injected-bug suite (`chaos/`)

Deliberately broken model variants with known signatures: fan-out join, wrong effective date on
territory, secure-view bypass, off-by-one fiscal boundary, a COALESCE that swallows a NULL segment.
CI asserts the harness catches all of them. A suite that has never caught a bug is not evidence; a
documented catch rate against seeded defects is.

### Failure taxonomy

Failures are classified, not counted: wrong join grain, fan-out double counting, wrong date boundary,
metric off the wrong column, NULL segment dropped, governance leak, governance over-block,
unresolvable. Per-category rates are the reported result, and the taxonomy is reusable by adopters.

### Blind-spot set

Questions the author did not write — generated against a public CRM/GTM schema whose structure the
author did not design, reference SQL written only after the question is fixed. Target ≥20% of total.
Reported separately, because the gap between blind-spot and authored scores *is* the measure of
author bias.

### The measured result

Every question runs through both arms — semantic-layer-constrained and direct-SQL — across all three
personas. Output is a per-category comparison, published in the README. If constraint does not help,
that is the published finding. A negative result honestly reported validates the methodology more
than a positive result that was never at risk.

## Adoption path

What makes this a reference architecture rather than a repository:

- `make deploy` provisions every object into any Snowflake account from scratch; `make teardown`
  removes them. Documented credit cost for a full deploy and eval run.
- `make eval` runs the suite and regenerates the results table.
- **Bring-your-own-models guide**: how to swap the reference warehouse for existing dbt models,
  which contracts must be authored, what the conformance suite requires.
- **Conformance suite**: the tests any deployment must pass — governance boundary, bypass
  resistance, answer-card completeness, invariant satisfaction. This is what makes "adopt the
  architecture" a checkable statement.
- **Architecture decision records** (`docs/adr/`): each significant choice, its alternatives, and
  why. The ADRs are the transferable artifact for a team deciding whether to follow the pattern.
- Versioned releases, so adopters can pin.

## Testing and CI

- `dbt test` on contracts, uniqueness, relationships, declared NULL policies
- pytest for the MCP server, with the governance boundary tested hardest: every bypass path has a
  test asserting it fails
- Evaluation suite on every PR; a regression in any failure category fails the build
- Injected-bug suite on every PR, 100% catch required
- Conformance suite runnable by adopters against their own deployment
- Secrets via environment and CI secret store, key-pair auth, nothing in the repository

## Error handling

Governance refusals are results, not exceptions — they populate `why_not` and score as correct when
the persona genuinely lacks access. Unresolvable questions return "cannot answer with available
metrics" rather than a guess, and that is scored too. Tool errors retry once, then surface with full
context. The agent never falls back to a less-governed path when a governed one fails.

## Out of scope

Real CRM integration. Writing or sending anything customer-facing. Multi-tenancy. Production
operations. Model training. Lead classification scenarios, which carry an unfixable circularity
problem when the data generator assigns the labels a classifier would recover.

## Honest limitations

A README section titled *"Why these evals might be lying to you"*: the residual circularity after
mitigation, selection bias in an author-chosen question set, the fact that synthetic data cannot
reproduce real CRM entropy — duplicate accounts, mid-quarter territory reassignment, half-filled
custom fields — and the specific conditions under which the headline result would not generalize.

For a reference architecture this section is load-bearing. A team deciding whether to adopt needs to
know where the evidence stops.

## Build sequence

- **Phase 0 — Evaluation spec.** Questions, reference SQL, personas, invariants, taxonomy. Committed
  before any model. This is the integrity claim and cannot be reordered.
- **Phase 1 — Warehouse and governance.** dbt models, roles, policies, secure views.
- **Phase 2 — Semantic layer.** Availability verification, then metric contracts.
- **Phase 3 — MCP server.** Tool surface, governance boundary, bypass tests.
- **Phase 4 — Agent and answer card.**
- **Phase 5 — Harness, chaos suite, CI gates.**
- **Phase 6 — Deployment tooling, ADRs, conformance suite, bring-your-own-models guide.**
- **Phase 7 — Run the experiment; publish results and limitations.**

Phases 1–6 each end green before the next begins.

## Success criteria

1. A stranger deploys it into a fresh Snowflake account with one command and it runs.
2. The README states the measured result in one sentence, with per-category rates for both arms
   across all three personas.
3. Git history shows the evaluation spec predates the models.
4. The injected-bug suite catches 100% of seeded defects, and the catch rate is published.
5. An adopting team can point the architecture at their own dbt models using the guide, and the
   conformance suite tells them whether they did it correctly.
6. The limitations section is specific enough to be useful to someone deciding against adoption.
