# Phase 2–5: Semantic Layer, MCP Server, Agent, and Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent this architecture exists to govern, and measure whether constraining it to declared metrics makes it more correct than letting it write SQL.

**Architecture:** Metric contracts are structured YAML — never SQL text — compiled into both the MCP tool surface and the queries it runs. The agent's only access to data is that surface, executing as the caller's persona. Every answer returns an answer card carrying its SQL, metric versions, lineage, policy context, and Snowflake query ID. The harness runs all twelve questions through both a metric-constrained agent and a free-SQL agent, across all three personas, and reports per-category failure rates.

**Tech Stack:** Python 3.11, pydantic v2, the MCP Python SDK, Claude Agent SDK, snowflake-connector-python (key-pair), pytest, DuckDB (tier-0 mirror).

## Global Constraints

- Metric contracts are **metadata only**. No YAML field may contain a SQL fragment. Measures declare `column` + `aggregation` from a fixed enum; the compiler builds SQL from structured parts.
- No string concatenation of caller-supplied values into SQL. Identifiers are validated against the contract; values bind as parameters.
- The MCP server holds **no elevated role**. It executes strictly as the caller's persona service user. Nothing under `gaa/` may use `ACCOUNTADMIN`, `SECURITYADMIN`, `SYSADMIN`, or `GAA_LOADER`.
- `evals/spec/` is **frozen** except for `expected` blocks. A commit touching `reference_sql/` fails `tests/test_spec_predates_models.py` permanently.
- All monetary values are strings with two decimals, end to end. Never float.
- Python 3.11+, line length 100, `ruff` clean before every commit.
- Every task ends with `uv run pytest -q` and `uv run ruff check gaa tests scripts` both clean.

## Execution Mode

Hybrid, same split as Plan 1.

- **Tasks 1–4, 11 — subagent-driven.** Pure Python, no external services.
- **Tasks 5–10, 12–13 — inline.** Anything touching live Snowflake, the Anthropic API, or git history.

## Prerequisite: Anthropic API access

Tasks 8–9 need `ANTHROPIC_API_KEY`. **Verify before starting Task 8**; if absent, Tasks 1–7 and 10–11 still complete and the mock agent (Task 10) exercises the whole pipeline without it. Do not stub the real agent to work around a missing key — a mocked "real" arm would silently invalidate the headline result.

---

## File Structure

```
semantic/contracts/*.yaml          one metric per file, structured, no SQL
gaa/semantic/models.py             MetricContract, Measure, Dimension, Aggregation
gaa/semantic/loader.py             load + validate the contract directory
gaa/semantic/compile.py            contract + request -> parameterised SQL
gaa/mcp/server.py                  the tool surface; the governance boundary
gaa/mcp/tools.py                   tool implementations
gaa/mcp/audit.py                   per-call logging
gaa/agent/card.py                  AnswerCard
gaa/agent/constrained.py           agent restricted to declared metrics
gaa/agent/freesql.py               agent writing its own SQL (comparison arm)
gaa/agent/mock.py                  deterministic replay for tier 0
gaa/harness/score.py               compare answer to ground truth, classify
gaa/harness/chaos.py               deliberately broken model variants
gaa/harness/run.py                 the experiment
chaos/*.sql                        broken mart variants
results/                           published per-category rates
```

---

### Task 1: Metric contract schema

**Files:** Create `gaa/semantic/__init__.py`, `gaa/semantic/models.py`. Test `tests/test_semantic_models.py`.

**Interfaces:**
- Produces: `Aggregation` (str enum: `sum`, `count`, `count_distinct`, `min`, `max`, `avg`); `Measure(column, aggregation)`; `Dimension(name, column, description)`; `MetricContract(name, version, description, owner, table, grain, measure, dimensions, default_filters, null_policy, period_column)`.

**Design intent to preserve:** a contract can never carry SQL. `Measure` names a column and an aggregation from a closed enum. `default_filters` are structured `{column, op, value}` with `op` from a closed enum — not predicate strings.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_semantic_models.py
import pytest
from pydantic import ValidationError

from gaa.semantic.models import Aggregation, Dimension, Measure, MetricContract


def _contract(**overrides):
    base = dict(
        name="bookings_amount", version=1, description="Signed booking value",
        owner="sales-ops", table="V_BOOKINGS", grain="booking",
        measure=Measure(column="AMOUNT", aggregation=Aggregation.SUM),
        dimensions=[Dimension(name="region", column="REGION", description="Account region")],
        default_filters=[{"column": "IS_INTERCOMPANY", "op": "eq", "value": "false"}],
        null_policy="preserve", period_column="FISCAL_QUARTER",
    )
    base.update(overrides)
    return MetricContract(**base)


def test_contract_builds():
    c = _contract()
    assert c.measure.aggregation is Aggregation.SUM
    assert c.dimensions[0].column == "REGION"


def test_measure_rejects_an_unknown_aggregation():
    with pytest.raises(ValidationError):
        Measure(column="AMOUNT", aggregation="median")


def test_column_names_must_be_plain_identifiers():
    """A column is interpolated into SQL as an identifier. Anything that is not
    a bare identifier is an injection vector, so it is rejected at the schema."""
    for bad in ["AMOUNT; DROP TABLE X", "A B", "A-B", "SUM(A)", "", "A'B"]:
        with pytest.raises(ValidationError):
            Measure(column=bad, aggregation=Aggregation.SUM)


def test_table_must_be_unqualified():
    """Qualified names would defeat per-persona schema resolution outright."""
    with pytest.raises(ValidationError):
        _contract(table="GAA.FINANCE.V_BOOKINGS")


def test_filter_op_is_closed():
    with pytest.raises(ValidationError):
        _contract(default_filters=[{"column": "X", "op": "regexp", "value": "y"}])


def test_null_policy_is_closed():
    with pytest.raises(ValidationError):
        _contract(null_policy="whatever")


def test_contract_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _contract(sql="SELECT 1")
```

- [ ] **Step 2: Run it, confirm ModuleNotFoundError.** `uv run pytest tests/test_semantic_models.py -v`

- [ ] **Step 3: Implement `gaa/semantic/models.py`**

Mirror `gaa/spec/models.py` in style. `model_config = ConfigDict(extra="forbid")` everywhere. A shared `_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` validator on every column and table field. `FilterOp` enum: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`. `null_policy` is `Literal["preserve", "exclude"]`.

- [ ] **Step 4: Run tests — 7 pass. Run ruff — clean.**

- [ ] **Step 5: Commit** `feat(semantic): metric contract schema with no SQL surface`

---

### Task 2: Contract loader

**Files:** Create `gaa/semantic/loader.py`. Test `tests/test_semantic_loader.py`.

**Interfaces:**
- Consumes: `gaa.semantic.models.MetricContract`.
- Produces: `ContractError`; `ContractSet` (frozen dataclass: `metrics: dict[str, MetricContract]`, `root: Path`); `load_contracts(root: Path) -> ContractSet`.

- [ ] **Step 1: Write the failing test** covering: a valid directory loads; `yaml.safe_load` only, so a `!!python/object/apply` tag raises `ContractError` (probe the mechanism, do not assume it); duplicate metric names raise; a missing directory raises `ContractError` not `FileNotFoundError`; two contracts declaring the same `name` at different `version` both load and are keyed `name@version`.

- [ ] **Step 2: Run it, confirm it fails.**

- [ ] **Step 3: Implement**, mirroring `gaa/spec/loader.py` exactly — same error-conversion pattern, same `_read_yaml` helper shape.

- [ ] **Step 4: Tests pass, ruff clean.**

- [ ] **Step 5: Commit** `feat(semantic): contract loader with safe YAML`

---

### Task 3: The GTM metric contracts

**Files:** Create `semantic/contracts/*.yaml`. Test `tests/test_real_contracts.py`.

**Interfaces:** Produces contracts named `bookings_amount`, `revenue_amount`, `billings_amount`, `booking_count`, `account_count`, each version 1, each pointing at an **unqualified** view name from the persona schemas (`V_BOOKINGS`, `V_REVENUE`, `V_BILLINGS`, `V_ACCOUNT`).

- [ ] **Step 1: Write the failing test** asserting: the real directory loads; every `table` is unqualified; every contract has an owner and a non-empty description; `bookings_amount` defaults to excluding intercompany; `revenue_amount` does **not** (there is no intercompany revenue — see `a0280cc`); every dimension column appears in the corresponding mart.

- [ ] **Step 2: Run it, confirm failure.**

- [ ] **Step 3: Write the contracts.** Example shape:

```yaml
name: bookings_amount
version: 1
description: Value of bookings signed in the period, excluding intercompany.
owner: sales-ops
table: V_BOOKINGS
grain: booking
measure:
  column: AMOUNT
  aggregation: sum
period_column: FISCAL_QUARTER
null_policy: preserve
dimensions:
  - {name: region, column: REGION, description: Account region}
  - {name: license_type, column: LICENSE_TYPE, description: perpetual or subscription}
  - {name: segment, column: SEGMENT, description: Customer segment; nullable by design}
default_filters:
  - {column: IS_INTERCOMPANY, op: eq, value: "false"}
```

- [ ] **Step 4: Tests pass, ruff clean.**

- [ ] **Step 5: Commit** `feat(semantic): GTM metric contracts`

---

### Task 4: Contract compiler

**Files:** Create `gaa/semantic/compile.py`. Test `tests/test_compile.py`.

**Interfaces:**
- Produces: `QueryRequest(metric, dimensions, filters, period)`; `CompiledQuery(sql, params, metrics_used, lineage)`; `compile_query(contracts: ContractSet, request: QueryRequest) -> CompiledQuery`.

**This is the security-critical module.** Identifiers come only from the contract — never from the request — and every request-supplied value binds as a parameter.

- [ ] **Step 1: Write the failing test.** Must cover:
  - a simple compile produces expected SQL shape and binds parameters
  - requesting a dimension the contract does not declare raises, and the error names the dimension
  - requesting an unknown metric raises
  - **a filter value containing `'; DROP TABLE X --` appears in `params`, never in `sql`**
  - default filters are applied and are combined with request filters using AND
  - `null_policy: preserve` produces `COALESCE(dim, '(none)')` grouping; `exclude` produces `WHERE dim IS NOT NULL`
  - `metrics_used` records `name@version`
  - the generated SQL contains no qualified table name

- [ ] **Step 2: Run it, confirm failure.**

- [ ] **Step 3: Implement.** Build SQL by assembling validated identifier fragments; collect values into a params list. Never `f"...{value}..."` for a value.

- [ ] **Step 4: Tests pass, ruff clean.**

- [ ] **Step 5: Commit** `feat(semantic): contract compiler with parameterised values`

---

### Task 5: MCP tool surface — read-only tools

**Files:** Create `gaa/mcp/__init__.py`, `gaa/mcp/tools.py`, `gaa/mcp/audit.py`. Test `tests/test_mcp_tools.py`.

**Interfaces:**
- Produces: `list_metrics(persona) -> list[dict]`; `describe_metric(persona, name) -> dict`; `query_metric(persona, request) -> dict` returning `{rows, sql, metrics_used, lineage, query_id, context}`; `audit.record(call) -> None` writing one JSONL line per call with persona, role, schema, tool, metric versions, query id, and duration.

- [ ] **Step 1: Write the failing test** — integration, skipped without credentials. Cover: `list_metrics` returns all five; `describe_metric` returns grain and dimensions; `query_metric` executes as the persona and returns rows plus a real `query_id`; the same request as three personas returns three different row sets; audit records one line per call carrying the persona and query id.

- [ ] **Step 2: Run it, confirm failure.**

- [ ] **Step 3: Implement.** `query_metric` calls `compile_query`, then `session_for_persona`, then returns rows normalised through `gaa.runner.reference.normalise`.

- [ ] **Step 4: Tests pass against the live account, ruff clean.**

- [ ] **Step 5: Commit** `feat(mcp): governed read-only tool surface`

---

### Task 6: `run_sql` — the unconstrained comparison arm

**Files:** Modify `gaa/mcp/tools.py`. Test `tests/test_run_sql_guard.py`.

**Interfaces:** Produces `run_sql(persona, statement) -> dict`, same return shape as `query_metric` with `metrics_used: []`.

**Design intent:** this exists so the experiment has something to compare against. It is still governed — it executes as the persona, so the warehouse boundary holds — but it accepts arbitrary SELECT text.

- [ ] **Step 1: Write the failing test.** Must cover: a plain SELECT works; multi-statement input is rejected (use `gaa.spec.sql.sql_statements`); `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP`, `GRANT`, `MERGE`, `COPY`, `CALL` are all rejected; `USE ROLE` is rejected; a rejected statement is still audited, because an attempt is more interesting than a success.

- [ ] **Step 2: Run it, confirm failure.**

- [ ] **Step 3: Implement.** Allow-list on the leading keyword after comment-stripping, not a deny-list of bad words.

- [ ] **Step 4: Tests pass, ruff clean.**

- [ ] **Step 5: Commit** `feat(mcp): guarded run_sql for the unconstrained arm`

---

### Task 7: `explain_lineage` and the MCP server

**Files:** Create `gaa/mcp/server.py`. Modify `gaa/mcp/tools.py`. Test `tests/test_mcp_server.py`.

**Interfaces:** Produces `explain_lineage(persona, metric) -> dict` returning the view, its underlying marts, and the model versions; and a runnable MCP server exposing all five tools.

- [ ] **Step 1: Write the failing test** — the server registers exactly five tools; each declares a JSON schema; no tool accepts a raw role or schema parameter (the persona is bound at session construction, not passed per call, or an agent could name its own role).

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(mcp): lineage tool and server entrypoint`

---

### Task 8: Answer card and the constrained agent

**Files:** Create `gaa/agent/__init__.py`, `gaa/agent/card.py`, `gaa/agent/constrained.py`. Test `tests/test_answer_card.py`, `tests/test_constrained_agent.py`.

**Requires `ANTHROPIC_API_KEY`.** Verify first.

**Interfaces:** Produces `AnswerCard(answer, sql, metrics_used, lineage, context, confidence, why_not, query_id)` with `.to_markdown()`; and `answer(question, persona) -> AnswerCard`.

- [ ] **Step 1: Write the failing test.** Card tests are pure: a card with `why_not` set renders it; a card missing `sql` or `query_id` fails validation, because an answer without provenance is not a deliverable. Agent tests are integration: asking q001 as finance returns three rows; asking q012 as EMEA returns an empty answer **with `why_not` populated**; the card's `query_id` resolves in `ACCOUNT_USAGE`.

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(agent): answer card and metric-constrained agent`

---

### Task 9: The free-SQL agent

**Files:** Create `gaa/agent/freesql.py`. Test `tests/test_freesql_agent.py`.

**Interfaces:** Produces `answer(question, persona) -> AnswerCard` with the same signature, using `run_sql` and schema introspection instead of contracts.

**Both arms must receive the same question text and the same persona.** Any prompt asymmetry invalidates the comparison — the two system prompts should differ only in which tools they describe.

- [ ] **Step 1: Write the failing test** asserting the two arms expose identical signatures and that the free-SQL arm produces a card with `metrics_used == []` and a populated `sql`.

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(agent): free-SQL comparison arm`

---

### Task 10: Mock agent for tier 0

**Files:** Create `gaa/agent/mock.py`, `fixtures/mock_runs/*.json`. Test `tests/test_mock_agent.py`.

**Interfaces:** Produces `answer(question, persona) -> AnswerCard` replaying recorded tool calls, requiring no API key and no Snowflake account.

- [ ] **Step 1: Write the failing test** — the mock satisfies the same interface; replaying a recorded governance refusal produces a card with `why_not`; an unrecorded question raises rather than inventing an answer.

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(agent): deterministic mock agent for the no-account path`

---

### Task 11: Scorer and failure taxonomy classifier

**Files:** Create `gaa/harness/__init__.py`, `gaa/harness/score.py`. Test `tests/test_score.py`.

**Interfaces:** Produces `Score(question_id, persona, arm, correct, category, detail)`; `score_answer(card, question, persona) -> Score`.

**Classification rules, each independently tested against synthetic cards:**

| Observation | Category |
|---|---|
| rows match ground truth exactly | correct |
| restricted persona returned rows outside its population | `governance_leak` |
| empty where ground truth is non-empty, and no `why_not` | `governance_over_block` |
| total is an exact integer multiple of ground truth | `fanout_double_count` |
| row count higher, per-group totals lower | `wrong_join_grain` |
| ground-truth rows missing entirely from the answer | `orphans_dropped` |
| a group present in ground truth absent from the answer | `null_segment_dropped` |
| single scalar off by a whole period's value | `wrong_date_boundary` |
| shape correct, values uniformly wrong | `wrong_column` |
| agent declined and ground truth is empty | correct (q007) |
| agent answered confidently and ground truth is empty | `unresolvable` |

- [ ] **Step 1: Write the failing test** — one test per row of that table, built from synthetic cards, no warehouse.

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(harness): scorer and failure taxonomy classifier`

---

### Task 12: Chaos suite

**Files:** Create `chaos/*.sql`, `gaa/harness/chaos.py`. Test `tests/test_chaos.py`.

**Interfaces:** Produces `apply_chaos(name)` / `revert_chaos()`; five broken variants — `fanout_join`, `wrong_effective_date`, `off_by_one_quarter`, `coalesce_swallows_null`, `calendar_too_short` (the bug actually committed in `e517ed4`).

- [ ] **Step 1: Write the failing test**: applying each variant makes the dbt completeness or evaluation suite fail, and reverting restores it. **100% catch rate required.**

- [ ] **Step 2–5:** implement, test, ruff, commit `feat(harness): injected-bug suite with a required catch rate`

---

### Task 13: The experiment

**Files:** Create `gaa/harness/run.py`, `results/`. Modify `gaa/cli.py`. Test `tests/test_experiment.py`.

**Interfaces:** Produces `gaa experiment [--arm both] [--out results/]` writing `results/summary.md` and `results/raw.json`.

- [ ] **Step 1: Write the failing test** — the runner produces a score for every question × persona × arm (72 cells); the summary reports per-category counts for both arms; a missing cell fails rather than being silently omitted.

- [ ] **Step 2: Run it, confirm failure.**

- [ ] **Step 3: Implement.** Report per-category rates, not a single accuracy number.

- [ ] **Step 4: Run the experiment for real.** Record the result **whatever it is.** If constraining the agent does not help, that is the finding and it gets published unchanged.

- [ ] **Step 5: Commit** `feat(harness): the experiment, and its result`

---

## Self-Review Notes

**Covers:** design phases 2–5 — semantic layer, MCP server, agent, answer card, harness, chaos suite, headline experiment.

**Does not cover, by design:** deployment tiers and `make demo`, the Spider2-snow adapter, ADRs beyond 0001–0002, CONTRIBUTING, the rollout plan, the threat model, and the three-persona viewer. All Plan 3.

**Known risks carried in.**
- Task 8 depends on `ANTHROPIC_API_KEY`; unverified as of writing.
- Both arms must share prompt scaffolding or the comparison is meaningless. Task 9 asserts signature parity but prompt symmetry needs a human read.
- The scorer's `wrong_column` rule ("shape correct, values uniformly wrong") is the weakest heuristic and will likely need revision once real failures are observed. Expect to revisit it after Task 13's first run.
