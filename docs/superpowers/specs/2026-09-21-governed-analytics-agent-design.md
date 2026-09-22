# Design — Governed Analytics Agent with Spec-First Evals

Date: 2026-09-21
Status: Draft for review
Working name: `governed-analytics-agent` (repo name not final)

## Purpose

One artifact, one job. The target is Snowflake's *Senior Director, Analytics Engineering, Data
Analytics & AI* (REQ20959). The résumé already evidences most of that JD — org leadership, Snowflake
RBAC and data contracts, dbt and Airflow, revenue-critical finance pipelines, Cortex deployments,
Claude Code agentic PR workflows. One duty it cannot evidence is the headline one:

> "Own Snowflake's internal analytics agents: Build, improve, and maintain general purpose analytics
> agents — and underlying context and semantic layers — that can be used across the organization
> including evals, orchestration instructions, and ground truth data sets"

This repo exists to prove that line, personally, in public. It is supporting evidence for an
application, not the application itself. It is deliberately **not** scoped to prove second-line
leadership, which no solo repo can.

## The question the repo answers

**Does constraining an analytics agent to a governed semantic layer make it measurably more correct
than letting it write SQL directly — and can we prove it with ground truth that we did not rig?**

That framing matters. It is Snowflake's own product thesis (semantic views, Cortex Analyst), stated
as a falsifiable claim and then tested. It is customer-zero behaviour rather than a description of
customer-zero behaviour. And it produces a headline result a reviewer can read in one sentence.

## Architecture

Five layers, bottom to top. Each is independently testable and has one job.

### 1. Warehouse (`warehouse/`)

Synthetic but structurally realistic GTM/revenue domain on Snowflake: accounts, opportunities,
bookings, ARR roll-forward, quota and territory assignment with effective dating, and a fiscal
calendar. dbt models, staged → intermediate → marts.

Non-negotiables, because a Snowflake director will check them:

- All monetary columns `NUMBER(38,2)`. Never `FLOAT`. Rounding artifacts would be
  indistinguishable from the "metric read off the wrong column" failure category.
- Explicit timezone handling. Source timestamps in UTC; a fiscal calendar dimension owns all
  period boundaries. No date arithmetic scattered through models.
- Territory and quota assignments are slowly-changing with effective dates. This is where real
  analytics agents fail, and omitting it would make the eval toy.
- NULL semantics declared per column in the contract. A silently dropped NULL segment is a
  scored failure category, so NULL handling cannot be accidental.

### 2. Governance (`warehouse/governance/`)

Snowflake-native, not simulated: RBAC role hierarchy, row access policies, masking policies, secure
views. Three personas:

| Persona | Sees | Realistic analogue |
|---|---|---|
| `FINANCE_GLOBAL` | everything | corporate FP&A |
| `SALES_DIR_EMEA` | EMEA territories only | regional sales leadership |
| `REP_INDIVIDUAL` | own accounts only | individual contributor |

The personas exist to generate **leak tests**, not to show that row access policies work. Every
director on that hiring committee writes row access policies weekly; demonstrating that they filter
rows proves nothing. What is worth proving is that an *agent* cannot get around them. The eval
therefore asserts bypass resistance explicitly: the agent must not reach restricted data by role
switching, default-role leakage, ownership chaining, querying unprotected base tables instead of
secure views, or inferring restricted values from aggregates.

### 3. Semantic layer (`semantic/`)

Versioned metric contracts in YAML, one file per metric. Each declares: name, description, owner,
grain, the measure expression, permitted dimensions, default filters, NULL policy, fiscal-period
binding, and a semantic version. The same YAML is the source for the MCP tool surface and compiles to
Snowflake semantic views.

Phase 2 opens with a verification step: confirm semantic view and Cortex Analyst availability for
this account's edition and region before building on either. If unavailable, the YAML contracts
remain the source of truth and compile to secure views instead; the tool surface and the experiment
are unaffected. The design does not depend on that feature being present.

This layer is the "context and semantic layers" half of the JD duty, and it is the thing whose value
the headline experiment measures.

### 4. MCP server (`mcp_server/`)

The agent's entire access surface. Tools:

- `list_metrics()` — discover available metrics
- `describe_metric(name)` — contract, grain, dimensions, NULL policy
- `query_metric(name, dimensions, filters, period)` — governed, parameterized execution
- `run_sql(statement)` — read-only, policy-enforced, available only in the unconstrained arm of
  the experiment
- `explain_lineage(name)` — objects touched, model versions

Design rules: no string concatenation into SQL anywhere; the server holds no elevated role and
executes strictly as the caller's persona; every call is logged with persona, role, policies in
effect, and model version. The server is the boundary where governance is enforced, so it gets the
strictest tests in the repo.

### 5. Agent (`agent/`)

Python, Claude Agent SDK. Given a natural-language question and a persona, it plans, resolves the
question to metrics and dimensions, calls tools, and returns an **answer card**:

```
answer:        the number(s)
sql:           exact statement executed
metrics_used:  name@version for each
lineage:       objects touched
context:       persona, role, policies in effect
confidence:    with stated basis
why_not:       populated when governance blocked part of the question
```

The answer card is the director-level artifact. A CDAO's concern is not whether an agent can answer a
question — it is whether the answer is auditable, attributable, and safe. Every response carries its
own audit trail, and `why_not` means a governance refusal is a first-class, legible outcome rather
than a silent wrong number.

## Evaluation methodology

### Spec-first ordering — the integrity mechanism

The eval spec is written and committed **before** any dbt model exists. Questions and reference SQL
land in Phase 0; models are then built to satisfy them. This ordering is visible in git history,
which converts "our evals are honest" from an assertion into something a skeptic can verify with
`git log`.

This directly addresses the circularity problem. Deterministic SQL removes label noise but does not
remove **specification circularity**: when one person authors the models, the questions, and the
reference queries, the eval can certify a wrong metric definition as ground truth. Spec-first
ordering plus the three mechanisms below is the mitigation. It is a mitigation, not a cure, and the
repo says so in plain language.

### Ground truth

Each question carries a deterministic reference SQL query written against base tables, independent of
the semantic layer, plus expected results per persona. Reference queries are minimal, assert their
grain explicitly, and are compiled against current model artifacts on every CI run so ground truth
cannot go stale.

### Metamorphic invariants

Properties that must hold regardless of the specific numbers, which catch a wrong oracle:

- `global == sum(regions)` for additive measures
- `rep ≤ region ≤ global` for any filtered measure
- masking changes distinct values but never row counts
- period-over-period sums reconcile to the annual roll-forward
- the same question asked twice returns identical results

### Injected-bug suite (`chaos/`)

Deliberately broken model variants, each with a known signature: a fan-out join, a wrong effective
date on territory assignment, a secure-view bypass, an off-by-one fiscal boundary, a COALESCE that
swallows a NULL segment. CI asserts the harness catches every one. An eval suite that has never
caught a bug is not evidence; a suite with a documented catch rate against seeded defects is.

### Failure taxonomy

Scored failures are classified, not just counted: wrong join grain, fan-out double counting, wrong
date boundary, metric read off the wrong column, NULL segment dropped, governance leak, governance
over-block, unresolvable question. Per-category rates are the reported result.

### Blind-spot set

A subset of questions the author did not write. Primary source: questions generated against a public
CRM/GTM dataset schema whose structure the author did not design, with reference SQL written only
after the question is fixed. Secondary source, if a reviewer is available: contributed questions.
Target is at least 20% of the total question count. Reported separately from the authored set,
because the gap between the two scores *is* the measure of author bias.

### The experiment

Every question runs through both arms — semantic-layer-constrained and direct-SQL — across all three
personas. The output is a per-category comparison. If constraint does not help, the repo reports
that. A negative result honestly reported is stronger evidence of judgment than a positive result
that was never at risk.

## Testing and CI

- `dbt test` on contracts, uniqueness, relationships, and declared NULL policies
- pytest for the MCP server, with the governance boundary tested hardest: every bypass path gets a
  test asserting it fails
- The eval suite runs on every PR; a regression in any failure category fails the build
- The injected-bug suite runs on every PR and must catch 100% of seeded defects
- Secrets via environment and CI secret store; nothing in the repo; connection uses key-pair auth

## Error handling

Governance refusals are results, not exceptions — they populate `why_not` and are scored as correct
when the persona genuinely lacks access. Unresolvable questions return an explicit "cannot answer
with available metrics" rather than a guess, and that is a scored outcome too. Tool errors are
retried once, then surfaced with full context. The agent never falls back to a less-governed path
when a governed one fails.

## Deliberately out of scope

Real CRM integration. Sending or writing anything customer-facing. Multi-tenancy. Production
operations. Model training. The dual-track B2C/B2B classification scenario from the original concept
— it was designed for a different employer and carries an unfixable circularity problem, since the
data generator assigns the very labels the classifier would recover.

## Honest limitations

A section in the README, written plainly, titled *"Why these evals might be lying to you."* It states
the residual circularity after the mitigations, the selection bias in an author-chosen question set,
the fact that synthetic data cannot reproduce real CRM entropy, and the specific conditions under
which the headline result would not generalize. This is the section most likely to be read closely
and it is the reason to write it well.

## Build sequence

- **Phase 0 — Eval spec.** Questions, reference SQL, personas, invariants, taxonomy. Committed
  before any model. This phase is the integrity claim; it cannot be reordered.
- **Phase 1 — Warehouse and governance.** dbt models, roles, policies, secure views. Built to
  satisfy Phase 0.
- **Phase 2 — Semantic layer.** Metric contracts; compile to semantic views.
- **Phase 3 — MCP server.** Tool surface, governance boundary, bypass tests.
- **Phase 4 — Agent and answer card.**
- **Phase 5 — Harness, chaos suite, CI gates.**
- **Phase 6 — Run the experiment, write the results and the limitations.**

Phases 1–5 each end green before the next begins.

## Success criteria

A reviewer with ten minutes can: read one sentence stating the headline result; see per-category
failure rates for both arms and all three personas; confirm from git history that the eval spec
predates the models; see the injected-bug catch rate; and read an honest account of what the evals
do not prove. If all five are true, the artifact has done its job.
