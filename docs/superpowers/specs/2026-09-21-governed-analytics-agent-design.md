# Safe, Auditable Analytics Agents on Snowflake

**Deploy it in a day. Prove it in CI.**

Date: 2026-09-21 (revised 2026-09-22)
Status: Draft for review
Working name: `governed-analytics-agent`

## The problem

An analytics agent that can query your warehouse can also leak it.

When a sales rep and a CFO ask the same question, does the agent return different answers — or does
it quietly return the CFO's number to the rep? When an agent-produced figure reaches a board deck,
can you reconstruct which SQL ran, under which role, against which policies? When a SOC 2 auditor
asks how you test your AI agents for data access violations, what do you show them?

Today, nothing open source answers these questions. Teams deploying agentic analytics are building
ad-hoc, undocumented, un-auditable solutions, or they are not deploying at all.

This is a deployable reference architecture and evaluation harness that answers all three, with
running code and a published measurement.

## What it is not

**This is not a text-to-SQL benchmark.** [Spider 2.0](https://github.com/xlang-ai/Spider2) (ICLR 2025
Oral, 872 stars) already evaluates language models on real-world enterprise text-to-SQL workflows,
including Snowflake and dbt subsets, and does it well. We use it rather than compete with it.

The distinction, stated once and clearly: **Spider 2.0 tells you whether the SQL is right. This tells
you whether the agent was allowed to run it, as whom, and whether you can prove it afterward.**

"Governance leak" and "governance over-block" are failure categories a correctness benchmark
structurally cannot express. That axis is where this work lives.

A Spider2-snow adapter (below) runs their task set through this harness and reports governance
deltas alongside correctness, so the two compose.

## Prior art

| Stars | Project | Covers | Does not cover |
|---|---|---|---|
| 25,366 | promptfoo | generic LLM/agent eval, red teaming | warehouse governance, persona execution |
| 20,887 | Cube | semantic layer for AI/BI | agent evaluation, access-policy enforcement |
| 2,581 | Malloy | data relationships language | agents, evaluation |
| 1,805 | MetricFlow | metrics as code | agents, evaluation |
| 872 | Spider 2.0 | enterprise text-to-SQL correctness, Snowflake + dbt | governance, personas, auditability |
| 766 | TAG-Bench | table-augmented generation | governance, personas |

Searches for `rbac aware agent`, `agent data access control eval`, `persona aware sql evaluation`,
`llm row level security`, `governed agent snowflake`, and `answer card lineage agent` returned zero
repositories on 2026-09-22.

**Provenance, kept accurate throughout:** built on a personal Snowflake account against synthetic GTM
data. The architecture, governance objects, agent, and evaluation harness are real and independently
reproducible. The data is not a real company's. Every claim here is verifiable by deploying it
yourself — credibility comes from reproducibility, not assertion.

## Design principles

1. **Deployability is a feature, not packaging.** An architecture nobody can run is a diagram. Time
   from clone to first answer card is a tracked metric with a budget.
2. **The agent's access surface is the governance boundary.** Not the prompt, not a policy document.
   Enforcement lives in one layer, testable in isolation.
3. **Every answer is auditable by construction.** An answer without its SQL, metric versions,
   lineage, policy context, and query ID is not a deliverable.
4. **Governance refusal is a first-class result.** "I can't see AMER" beats a silently smaller number.
5. **The evaluation is adversarial toward its own author.** Mechanisms that could certify the
   author's own mistakes are defects to engineer out.
6. **Snowflake-native now, portable later if ever.** Depth on one platform beats shallow coverage of
   three. But the seams that would carry portability — policy evaluation, audit sink, contract
   compiler target — stay clean interfaces rather than Snowflake calls scattered through the agent.
   No BigQuery or Databricks adapters are built. The option to add them is kept open and unpaid for.

## Deployability (first-class constraint)

Three entry points, ordered by how much the reader has to commit:

**Tier 0 — no account, no API key, 5 minutes.** `make demo` runs the full pipeline against a local
DuckDB mirror with a **mock agent** replaying recorded tool calls. The reader sees real answer cards,
real governance blocks, real audit records, and a real eval report without provisioning anything or
spending a credit. This tier exists solely so a skeptical reader reaches the "aha" before deciding
whether to invest.

**Tier 1 — own Snowflake account, under one hour.** `make deploy` provisions every object from
scratch: warehouse, roles, per-persona schemas, secure views, dbt models, semantic views, sample
data, three personas. `make eval` runs the suite and regenerates the results table.
`make teardown` removes everything. Credit cost for a full deploy-and-eval cycle is documented.

**Tier 2 — own models.** The bring-your-own-models guide: swap the reference warehouse for existing
dbt models, author the metric contracts, run the conformance suite to find out whether you did it
correctly.

The one-hour budget for Tier 1 is a hard design constraint. Any component that would push past it
gets pre-built and configured rather than extended.

## Architecture

Five layers, each independently testable and replaceable.

### 1. Warehouse (`warehouse/`)

Three reconcilable facts, because the reconciliation between them is where the interesting failures
live:

```
FCT_BOOKINGS   booking_id, account_id, booking_date, amount, license_type
               (perpetual|subscription), term_months, region, owner_rep_id,
               is_intercompany
FCT_BILLINGS   billing_id, booking_id, invoice_date, amount
FCT_REVENUE    revenue_id, booking_id, recognition_date, amount
```

Plus `DIM_ACCOUNT`, `DIM_TERRITORY_SCD` (effective-dated), `DIM_QUOTA` (effective-dated), and
`DIM_FISCAL_CALENDAR`. dbt models, staged → intermediate → marts. Fiscal year is the **calendar
year**: 2026-Q3 is 1 July to 30 September 2026.

**Recognition follows license type.** Perpetual recognizes in full on the booking date; subscription
recognizes ratably across `term_months`. Identical signed amounts, entirely different revenue
timing — which makes *"why doesn't my booking show up in revenue?"* a question with a correct,
auditable answer that a naive agent gets wrong.

**The reconciliation rule:** every booking should appear in billings and have revenue recorded. The
generated data deliberately violates it in known places. Asked to reconcile, an agent writes an
INNER JOIN, silently drops the unmatched rows, and reports that everything ties out — a false answer
shaped like good news. Finding the orphans is the test.

GTM is the **worked example**, not the product. Adopters replace this layer wholesale. It exists so
the reference deployment runs end to end and so the failure taxonomy has realistic material.

Non-negotiables:

- Monetary columns `NUMBER(38,2)`. Never `FLOAT` — rounding artifacts are indistinguishable from
  real metric errors and would corrupt the evaluation.
- Source timestamps UTC; `DIM_FISCAL_CALENDAR` owns every period boundary.
- Territory and quota assignments slowly-changing with effective dates. This is where real analytics
  agents fail: they apply today's territory to last quarter's bookings.
- NULL semantics declared per column, because a dropped NULL segment is a scored failure category.

All data is synthetic, produced by a generic profile-driven generator rather than a fixture script.
See `docs/adr/0002-synthetic-data-no-admin-ui-deferred-deal-intelligence.md`.

### 2. Governance (`warehouse/governance/`)

Snowflake-native, and built on Standard Edition so that any account can deploy it. Row access
policies and masking policies are Enterprise-gated; the development account is Standard, so the
boundary is implemented as **one schema per persona containing identically-named secure views**,
with each role granted exactly one schema. See `docs/adr/0001-governance-on-standard-edition.md`
for the decision, the alternatives, and what this costs.

| Persona | Schema | Sees | Analogue |
|---|---|---|---|
| `FINANCE_GLOBAL` | `GAA.FINANCE` | all territories, unmasked names | corporate FP&A |
| `SALES_DIR_EMEA` | `GAA.EMEA` | EMEA only, masked names | regional sales leadership |
| `REP_INDIVIDUAL` | `GAA.REP` | own accounts only, masked names | individual contributor |

Reference SQL uses **unqualified** table names. Each persona session sets its own default schema,
so identical SQL text resolves to a different view per persona — which is what keeps "same
question, three different correct answers" a real property rather than three different queries.
Masking is emulated inside the restricted views by hashing `ACCOUNT_NAME`, preserving row counts
while changing distinct values.

The personas generate **leak tests**. Demonstrating that a filtered view returns fewer rows proves
nothing. The claim is that an *agent* cannot get around the boundary, and the conformance suite
asserts it against every bypass path: switching roles, reading another persona's schema, reading
the base tables in `MARTS`, and inferring restricted values from aggregates.

Because grants rather than table-attached policies carry the boundary here, a mis-grant exposes a
whole schema. The conformance suite therefore tests grants adversarially, and the threat model
treats mis-granted schema access as a primary failure mode.

### 3. Semantic layer (`semantic/`)

Versioned metric contracts in YAML — name, description, owner, grain, measure expression, permitted
dimensions, default filters, NULL policy, fiscal-period binding, semantic version. One source for
both the Snowflake semantic views and the agent tool surface, so the agent cannot drift from the
contract.

Phase 2 opens by verifying semantic view and Cortex Analyst availability for the target account's
edition and region. If unavailable, contracts compile to secure views instead; tool surface and
evaluation are unaffected.

### 4. MCP server (`mcp_server/`)

The agent's entire access surface.

- `list_metrics()` — discovery
- `describe_metric(name)` — contract, grain, dimensions, NULL policy
- `query_metric(name, dimensions, filters, period)` — governed, parameterized
- `run_sql(statement)` — read-only, policy-enforced; the unconstrained comparison arm
- `explain_lineage(name)` — objects touched, model versions

Rules: no string concatenation into SQL anywhere; the server holds no elevated role and executes
strictly as the caller's persona; every call logged with persona, role, policies in effect, and model
version. The safety claim lives here, so this layer carries the strictest tests.

### 5. Agent (`agent/`)

Python, Claude Agent SDK. Takes a question and a persona; plans, resolves to metrics and dimensions,
calls tools, returns an **answer card**:

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

The answer card is the README's first screenshot. `query_id` means every answer traces to a row in
Snowflake's own query history, so adopters audit agent behaviour with tooling they already run.

A mock agent implementing the same interface backs Tier 0.

## Evaluation methodology

### Spec-first ordering

The evaluation spec — questions and deterministic reference SQL — is committed **before** any dbt
model exists. Models are built to satisfy it. Visible in `git log`, which converts "these evals are
honest" from an assertion into something a skeptic verifies.

This addresses specification circularity: deterministic SQL removes label noise, but when one author
writes the models, the questions, *and* the reference queries, the evaluation can certify a wrong
metric definition as ground truth. Spec-first plus the mechanisms below is a mitigation, not a cure,
and the documentation says so.

### Ground truth

Deterministic reference SQL against base tables, independent of the semantic layer, with expected
results per persona. Minimal queries, explicit grain assertions, recompiled against current model
artifacts every CI run so ground truth cannot go stale.

### Metamorphic invariants

Properties that hold regardless of the numbers, catching a wrong oracle: `global == sum(regions)` for
additive measures; `rep ≤ region ≤ global` for any filtered measure; masking changes distinct values
but never row counts; period sums reconcile to the annual roll-forward; identical questions return
identical results.

### Injected-bug suite (`chaos/`)

Deliberately broken model variants with known signatures: fan-out join, wrong effective date on
territory, secure-view bypass, off-by-one fiscal boundary, a COALESCE swallowing a NULL segment. CI
asserts a 100% catch rate — and that bar ships working, not aspirational. A suite that has never
caught a bug is not evidence.

### Failure taxonomy

Classified, not counted: wrong join grain, fan-out double counting, wrong date boundary, metric off
the wrong column, NULL segment dropped, governance leak, governance over-block, unresolvable.
Per-category rates are the published result, and the taxonomy is reusable by adopters.

### Spider2-snow adapter (`adapters/spider2/`)

Runs Spider 2.0's Snowflake task set through this harness, reporting governance categories alongside
correctness. Two payoffs: the question set is authored by someone else against schemas the author did
not design, which is the strongest available answer to author bias; and results become legible in
terms an established, peer-reviewed benchmark already made standard.

### The measured result

Every question runs through both arms — semantic-layer-constrained and direct-SQL — across all three
personas. Per-category comparison published in the README. If constraint does not help, that is the
published finding. A negative result honestly reported validates the methodology more than a positive
result that was never at risk.

## Adoption path

- Tiers 0/1/2 above, with `make demo`, `make deploy`, `make eval`, `make teardown`
- **Conformance suite** — the tests any deployment must pass: governance boundary, bypass resistance,
  answer-card completeness, invariant satisfaction. This makes "adopt this architecture" checkable.
- **Architecture decision records** (`docs/adr/`) — each significant choice, alternatives, reasoning.
  The transferable artifact for a team deciding whether to follow the pattern.
- **CONTRIBUTING.md** — explicit co-maintainer invitation. A single-maintainer reference architecture
  is a risk adopters correctly price in; the project states up front that it is looking for
  co-maintainers and documents what taking over a layer involves.
- Versioned releases so adopters can pin.

## Non-code deliverables

Code proves the engineering. These two documents prove the judgment, and they are the reason a
reader who evaluates operating capability rather than craft has something to read.

### 90-day rollout plan (`docs/rollout-plan.md`)

How an organization actually adopts this, written as an operator would write it rather than as a
README.

- **Phase 1 (days 1–30)** — sandbox deployment; red-team the governance boundary; establish the
  baseline leak and over-block rates before anyone trusts an answer.
- **Phase 2 (days 31–60)** — a limited persona set against the ten highest-value finance and sales
  questions; humans verify every answer; the eval suite runs on every model change.
- **Phase 3 (days 61–90)** — expand domains; add monitoring and an incident process for a wrong
  answer that reached a decision.

With staffing shape per phase, success metrics (governance leak rate, over-block rate, eval pass
rate, time-to-answer, credit cost per answer), a risk register, and the explicit criteria for
stopping or rolling back.

### Threat model and control mapping (`docs/threat-model.md`)

Two pages. Each failure mode enumerated, then mapped to the control that exists in the code and the
test that proves the control works:

- prompt injection reaching the tool surface
- tool misuse and parameter tampering
- role escalation and default-role leakage
- exfiltration via aggregates and inference attacks
- metric-contract tampering as a data-definition injection path
- audit-log leakage, where the log itself exposes SQL, policy definitions, and schema shape
- supply-chain compromise of the CI evaluation path

Failure modes without an implemented control are listed as accepted risk with the reason, rather
than omitted. A threat model that claims complete coverage is not credible.

### Walkthrough recording

Five to seven minutes: a blocked query showing `why_not`, an allowed query showing its `query_id`,
and the audit lookup reconciling that query ID against `ACCOUNT_USAGE`. Linked from the README above
the fold, because the fastest path to belief is watching it happen.

## Testing and CI

- `dbt test` on contracts, uniqueness, relationships, declared NULL policies
- pytest for the MCP server; every bypass path has a test asserting it fails
- Evaluation suite on every PR; regression in any failure category fails the build
- Injected-bug suite on every PR, 100% catch required
- Tier 0 demo runs in CI, so the no-account path can never silently break
- Secrets via environment and CI secret store, key-pair auth, nothing in the repository

## Error handling

Governance refusals are results, not exceptions — they populate `why_not` and score as correct when
the persona genuinely lacks access. Unresolvable questions return "cannot answer with available
metrics" rather than a guess, scored as its own outcome. Tool errors retry once, then surface with
full context. The agent never falls back to a less-governed path when a governed one fails.

## Out of scope

Real CRM integration. Writing or sending anything customer-facing. Multi-tenancy. Production
operations. Model training. Lead-classification scenarios, which carry unfixable circularity when the
data generator assigns the labels a classifier would recover.

## Honest limitations

A README section titled *"Why these evals might be lying to you"*: residual circularity after
mitigation, selection bias in an author-chosen question set, the fact that synthetic data cannot
reproduce real CRM entropy — duplicate accounts, mid-quarter territory reassignment, half-filled
custom fields — and the conditions under which the headline result would not generalize.

For a reference architecture this section is load-bearing. A team deciding whether to adopt needs to
know where the evidence stops.

## Demand validation (before Phase 1)

Cheap tests, run before committing weeks of build:

- Search what practitioners actually search — `Snowflake row level security LLM`, `agent query
  audit`, `MCP Snowflake security` — rather than the category label.
- Post the **problem statement**, not the category name, in the dbt community Slack and Snowflake
  community channels. "We're wrestling with exactly this" confirms the gap; indifference disconfirms.
- Ask the author's own network of data leaders whether they would deploy an agent against production
  Snowflake today, and what would have to be true first.

If these come back cold, the scope is wrong and better to know in week one.

## Build sequence

- **Phase 0 — Evaluation spec.** Questions, reference SQL, personas, invariants, taxonomy. Committed
  before any model. The integrity claim; cannot be reordered.
- **Phase 1 — Warehouse and governance.** dbt models, roles, policies, secure views.
- **Phase 2 — Semantic layer.** Availability verification, then metric contracts.
- **Phase 3 — MCP server.** Tool surface, governance boundary, bypass tests.
- **Phase 4 — Agent, answer card, and mock agent.**
- **Phase 5 — Harness, chaos suite, CI gates.**
- **Phase 6 — Tier 0 demo path, deployment tooling, conformance suite, ADRs, CONTRIBUTING,
  bring-your-own-models guide.**
- **Phase 7 — Spider2-snow adapter; run the experiment; publish results and limitations.**
- **Phase 8 — Non-code deliverables: 90-day rollout plan, threat model and control mapping,
  walkthrough recording.**

Phases 1–6 each end green before the next begins.

The threat model is drafted during Phase 3, when the governance boundary is being built and its
failure modes are fresh, then finalized in Phase 8 once the controls and their tests exist.

## Success criteria

Stars are the wrong metric — reference architectures are cloned, forked, and quietly copied into
company repos, not starred. What counts:

1. A stranger runs `make demo` with no Snowflake account and no API key, and sees a real answer card
   and governance block inside five minutes.
2. A stranger deploys to a fresh Snowflake account in under an hour.
3. The README states the measured result in one sentence, with per-category rates for both arms
   across all three personas.
4. `git log` shows the evaluation spec predates the models.
5. The injected-bug suite catches 100% of seeded defects, published.
6. An adopting team points the architecture at their own dbt models and the conformance suite tells
   them whether they got it right.
7. At least one external contributor or co-maintainer.
8. A reader who evaluates operating capability rather than code — a data leader deciding whether to
   adopt, or a hiring committee filling a leadership seat — finds the rollout plan and threat model
   and can tell from them how the author would run this at scale.
