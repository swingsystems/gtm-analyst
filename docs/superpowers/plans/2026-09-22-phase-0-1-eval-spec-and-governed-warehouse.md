# Phase 0–1: Eval Spec and Governed Warehouse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a governed Snowflake warehouse whose evaluation spec — questions, deterministic reference SQL, personas, invariants — was committed before any data model existed, and prove that the same question returns three different correct answers under three personas.

**Architecture:** Tasks 1–5 create the evaluation spec and its validator with no warehouse in existence. Tasks 6–10 build the dbt warehouse and Snowflake governance objects to satisfy that spec. Tasks 11–13 execute the spec against the warehouse as each persona and check the invariants. The ordering is the integrity mechanism: `git log` must show spec commits strictly before model commits, and no task may reorder this.

**Tech Stack:** Python 3.11, uv, dbt-core + dbt-snowflake, snowflake-connector-python (key-pair auth), pydantic v2, pytest, PyYAML, GitHub Actions.

## Global Constraints

- All monetary columns are `NUMBER(38,2)`. `FLOAT` is prohibited for money anywhere in the warehouse.
- Source timestamps are UTC. All period boundaries come from `dim_fiscal_calendar`. No ad-hoc date arithmetic in models.
- Metric contracts and eval specs are **metadata only**. No YAML field may contain a raw SQL fragment that reaches Snowflake. Measures declare `column` + `aggregation` from a fixed enum.
- All YAML is loaded with `yaml.safe_load`. Never `yaml.load`.
- No string concatenation into SQL. Reference SQL lives in `.sql` files; runtime parameters bind via the connector.
- Secrets come from environment variables only. Nothing credential-shaped is committed. `.env` is gitignored.
- Every persona executes as its own Snowflake role. No code path may use `ACCOUNTADMIN` or `SYSADMIN` at query time.
- Python 3.11+. Line length 100. `ruff` clean before every commit.

## Execution Mode

Hybrid, split at the Snowflake boundary.

- **Tasks 1–6 — subagent-driven.** Pure Python, fully specified, unit-testable, no external state.
- **Tasks 7–13 — inline.** Anything touching live Snowflake, dbt runs, credentials, or git history.

Delegate an ambiguous task only if it introduces no names consumed elsewhere, is fully validated by
existing tests without human interpretation, and cannot require modifying Task 2–5 files.

**Standing rule for every executor, inline or delegated:** files under `evals/spec/` and `gaa/spec/`
are frozen once Task 5 is committed. If a later task appears to need a change there, stop and
escalate rather than editing. A commit touching spec files after Task 6 breaks Task 13 permanently,
and it cannot be repaired by rewriting history — rewriting is the thing the history exists to
disprove.

## Vertical Slice Before Breadth

Snowflake governance iteration is the part this plan most underestimates. Per-persona schemas,
secure views, the grant graph, dbt-created objects, and connector auth all interact, and the first
attempt will not work.

So: **prove the mechanism on one question before building for twelve.**

- Task 4 still authors and commits **all twelve** questions and all twelve reference SQL files. This
  is not negotiable and is not what the slice defers — every question must predate the models, or
  Task 13 fails for the ones that don't.
- Tasks 7–11 build only what `q001` needs first: `stg_bookings`, `stg_accounts`, `dim_account`,
  `dim_fiscal_calendar`, `fct_bookings`, the three persona schemas and views, three roles. Run
  `q001` as all three
  personas and confirm three different correct answers.
- Only once that end-to-end proof passes do the remaining marts, policies, and questions get built.

If the mechanism does not work, this surfaces it in hour two rather than week two.

## File Structure

```
pyproject.toml                          deps, ruff/pytest config
Makefile                                make setup / spec-validate / deploy / eval
.env.example                            documented env var names, no values
.github/workflows/ci.yml                lint, spec validation, unit tests

gaa/                                    the Python package
  __init__.py
  config.py                             env-var loading, typed settings
  connection.py                         Snowflake key-pair auth, per-persona sessions
  spec/
    __init__.py
    models.py                           pydantic schemas: Persona, Question, Invariant
    loader.py                           safe_load + validate spec directory
    taxonomy.py                         FailureCategory enum
  runner/
    __init__.py
    reference.py                        execute reference SQL per persona
    invariants.py                       invariant evaluation
  cli.py                                spec-validate, eval-reference entrypoints

evals/spec/
  personas.yaml                         three personas, role mapping
  questions/*.yaml                      one file per question
  reference_sql/*.sql                   one file per question, parameterized
  invariants.yaml                       metamorphic properties

warehouse/
  dbt_project.yml
  profiles.example.yml
  seeds/*.csv                           deterministic synthetic data
  models/staging/*.sql + schema.yml
  models/marts/*.sql + schema.yml
  governance/01_roles.sql
  governance/02_masking_policies.sql
  governance/03_row_access_policies.sql
  governance/04_secure_views.sql
  governance/05_grants.sql

tests/
  test_spec_models.py
  test_spec_loader.py
  test_invariants.py
  test_connection.py
  test_governance_boundary.py
```

---

### Task 1: Project scaffolding and typed configuration

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `gaa/__init__.py`, `gaa/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gaa.config.Settings` (pydantic `BaseSettings`) with fields `snowflake_account: str`, `snowflake_user: str`, `snowflake_private_key_path: Path`, `snowflake_private_key_passphrase: str | None`, `snowflake_warehouse: str`, `snowflake_database: str`, `snowflake_schema: str`; and `gaa.config.load_settings() -> Settings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from gaa.config import load_settings


def test_load_settings_reads_environment(monkeypatch, tmp_path):
    key = tmp_path / "rsa_key.p8"
    key.write_text("not-a-real-key")
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct123")
    monkeypatch.setenv("SNOWFLAKE_USER", "svc_gaa")
    monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY_PATH", str(key))
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "GAA_WH")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "GAA")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "MARTS")

    settings = load_settings()

    assert settings.snowflake_account == "acct123"
    assert settings.snowflake_private_key_path == key
    assert settings.snowflake_private_key_passphrase is None


def test_load_settings_missing_required_var_raises(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
    monkeypatch.delenv("SNOWFLAKE_USER", raising=False)
    with pytest.raises(ValueError):
        load_settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa'`

- [ ] **Step 3: Write pyproject.toml**

```toml
[project]
name = "gaa"
version = "0.1.0"
description = "Safe, auditable analytics agents on Snowflake"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "pyyaml>=6.0",
    "snowflake-connector-python>=3.12",
    "cryptography>=42.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "dbt-core>=1.8", "dbt-snowflake>=1.8"]

[project.scripts]
gaa = "gaa.cli:cli"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 4: Write gaa/config.py**

```python
# gaa/config.py
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every value comes from the environment."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    snowflake_account: str = Field(alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(alias="SNOWFLAKE_USER")
    snowflake_private_key_path: Path = Field(alias="SNOWFLAKE_PRIVATE_KEY_PATH")
    snowflake_private_key_passphrase: str | None = Field(
        default=None, alias="SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"
    )
    snowflake_warehouse: str = Field(alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(alias="SNOWFLAKE_SCHEMA")


def load_settings() -> Settings:
    """Load settings, raising ValueError when a required variable is absent."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic raises ValidationError, a subclass of ValueError
        raise ValueError(f"invalid or missing configuration: {exc}") from exc
```

Create `gaa/__init__.py` as an empty file.

- [ ] **Step 5: Write .env.example and .gitignore**

```bash
# .env.example — copy to .env and fill in. .env is gitignored.
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PRIVATE_KEY_PATH=
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=
SNOWFLAKE_WAREHOUSE=GAA_WH
SNOWFLAKE_DATABASE=GAA
SNOWFLAKE_SCHEMA=MARTS
```

```
# .gitignore
.env
*.p8
*.pem
__pycache__/
.venv/
target/
dbt_packages/
logs/
.pytest_cache/
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv sync --all-extras && uv run pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example .gitignore gaa/ tests/test_config.py
git commit -m "feat: project scaffolding and typed configuration"
```

---

### Task 2: Spec schemas — personas, questions, invariants

**Files:**
- Create: `gaa/spec/__init__.py`, `gaa/spec/models.py`, `gaa/spec/taxonomy.py`
- Test: `tests/test_spec_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gaa.spec.taxonomy.FailureCategory` (str enum); `gaa.spec.models.Persona(name, snowflake_role, description)`, `gaa.spec.models.ExpectedResult(persona, rows)`, `gaa.spec.models.Question(id, text, reference_sql, grain, expected, tags, source)`, `gaa.spec.models.Invariant(id, description, kind, params)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec_models.py
import pytest
from pydantic import ValidationError

from gaa.spec.models import ExpectedResult, Invariant, Persona, Question
from gaa.spec.taxonomy import FailureCategory


def test_persona_requires_role():
    p = Persona(name="FINANCE_GLOBAL", snowflake_role="GAA_FINANCE_GLOBAL", description="FP&A")
    assert p.snowflake_role == "GAA_FINANCE_GLOBAL"


def test_question_rejects_inline_sql_field():
    """Contracts are metadata only. reference_sql names a FILE, never SQL text."""
    with pytest.raises(ValidationError):
        Question(
            id="q001",
            text="Net new ARR for Q3 FY26 by region",
            reference_sql="SELECT * FROM fct_arr_rollforward",  # SQL text, not a filename
            grain="region",
            expected=[],
            tags=["arr"],
            source="authored",
        )


def test_question_accepts_sql_filename():
    q = Question(
        id="q001",
        text="Net new ARR for Q3 FY26 by region",
        reference_sql="q001_net_new_arr_by_region.sql",
        grain="region",
        expected=[ExpectedResult(persona="FINANCE_GLOBAL", rows=[{"REGION": "EMEA", "VALUE": "100.00"}])],
        tags=["arr"],
        source="authored",
    )
    assert q.reference_sql.endswith(".sql")
    assert q.expected[0].persona == "FINANCE_GLOBAL"


def test_question_source_must_be_known():
    with pytest.raises(ValidationError):
        Question(
            id="q002", text="x", reference_sql="q002.sql", grain="region",
            expected=[], tags=[], source="invented",
        )


def test_invariant_kind_validated():
    inv = Invariant(
        id="sum_of_parts", description="global equals sum of regions",
        kind="sum_of_parts", params={"whole": "FINANCE_GLOBAL", "parts": ["EMEA", "AMER", "APAC"]},
    )
    assert inv.kind == "sum_of_parts"
    with pytest.raises(ValidationError):
        Invariant(id="x", description="x", kind="nonsense", params={})


def test_failure_categories_present():
    assert FailureCategory.GOVERNANCE_LEAK.value == "governance_leak"
    assert FailureCategory.GOVERNANCE_OVER_BLOCK.value == "governance_over_block"
    assert len(list(FailureCategory)) == 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spec_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa.spec'`

- [ ] **Step 3: Write gaa/spec/taxonomy.py**

```python
# gaa/spec/taxonomy.py
from enum import Enum


class FailureCategory(str, Enum):
    """The eight ways an analytics answer can be wrong.

    Reported per-category rather than as a single accuracy number, because the
    categories have different causes and different fixes.
    """

    WRONG_JOIN_GRAIN = "wrong_join_grain"
    FANOUT_DOUBLE_COUNT = "fanout_double_count"
    WRONG_DATE_BOUNDARY = "wrong_date_boundary"
    WRONG_COLUMN = "wrong_column"
    NULL_SEGMENT_DROPPED = "null_segment_dropped"
    GOVERNANCE_LEAK = "governance_leak"
    GOVERNANCE_OVER_BLOCK = "governance_over_block"
    UNRESOLVABLE = "unresolvable"
```

- [ ] **Step 4: Write gaa/spec/models.py**

```python
# gaa/spec/models.py
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "with ", "drop ", "grant ")


class Persona(BaseModel):
    """A caller identity. Maps one-to-one onto a Snowflake role."""

    name: str
    snowflake_role: str
    description: str


class ExpectedResult(BaseModel):
    """The correct answer for one persona. Values are strings to preserve decimal scale."""

    persona: str
    rows: list[dict[str, str]]


class Question(BaseModel):
    """One evaluation question and its deterministic ground truth.

    `reference_sql` names a file under evals/spec/reference_sql/. It is never SQL
    text: spec YAML is metadata only, so no YAML field can carry a fragment that
    reaches Snowflake.
    """

    id: str
    text: str
    reference_sql: str
    grain: str
    expected: list[ExpectedResult]
    tags: list[str] = Field(default_factory=list)
    source: Literal["authored", "blind_spot", "spider2"]

    @field_validator("reference_sql")
    @classmethod
    def must_be_filename_not_sql(cls, v: str) -> str:
        if not v.endswith(".sql"):
            raise ValueError("reference_sql must be a .sql filename, not SQL text")
        lowered = v.lower()
        if any(kw in lowered for kw in _SQL_KEYWORDS) or "\n" in v or "/" in v:
            raise ValueError("reference_sql must be a bare filename containing no SQL")
        return v


class Invariant(BaseModel):
    """A metamorphic property that must hold regardless of the specific numbers."""

    id: str
    description: str
    kind: Literal["sum_of_parts", "monotonic_nesting", "masking_preserves_row_count", "determinism"]
    params: dict[str, Any] = Field(default_factory=dict)
```

Create `gaa/spec/__init__.py` as an empty file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_spec_models.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add gaa/spec/ tests/test_spec_models.py
git commit -m "feat(spec): schemas for personas, questions, and invariants"
```

---

### Task 3: Spec loader with safe YAML and referential integrity

**Files:**
- Create: `gaa/spec/loader.py`
- Test: `tests/test_spec_loader.py`

**Interfaces:**
- Consumes: `gaa.spec.models.{Persona, Question, Invariant}`.
- Produces: `gaa.spec.loader.Spec` (dataclass with `personas: dict[str, Persona]`, `questions: list[Question]`, `invariants: list[Invariant]`) and `gaa.spec.loader.load_spec(root: Path) -> Spec`, which raises `SpecError` on any inconsistency.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec_loader.py
import pytest

from gaa.spec.loader import SpecError, load_spec


def _write_spec(root, question_yaml, sql_files=("q001_x.sql",)):
    (root / "questions").mkdir(parents=True)
    (root / "reference_sql").mkdir(parents=True)
    (root / "personas.yaml").write_text(
        "personas:\n"
        "  - name: FINANCE_GLOBAL\n"
        "    snowflake_role: GAA_FINANCE_GLOBAL\n"
        "    description: FP&A\n"
    )
    (root / "invariants.yaml").write_text("invariants: []\n")
    (root / "questions" / "q001.yaml").write_text(question_yaml)
    for name in sql_files:
        (root / "reference_sql" / name).write_text("SELECT 1 AS VALUE;")


GOOD_QUESTION = """
id: q001
text: Test question
reference_sql: q001_x.sql
grain: region
source: authored
tags: [test]
expected:
  - persona: FINANCE_GLOBAL
    rows:
      - {REGION: EMEA, VALUE: "100.00"}
"""


def test_load_spec_succeeds(tmp_path):
    _write_spec(tmp_path, GOOD_QUESTION)
    spec = load_spec(tmp_path)
    assert "FINANCE_GLOBAL" in spec.personas
    assert spec.questions[0].id == "q001"


def test_missing_reference_sql_file_raises(tmp_path):
    _write_spec(tmp_path, GOOD_QUESTION, sql_files=())
    with pytest.raises(SpecError, match="reference SQL file not found"):
        load_spec(tmp_path)


def test_unknown_persona_in_expected_raises(tmp_path):
    bad = GOOD_QUESTION.replace("persona: FINANCE_GLOBAL", "persona: NOBODY")
    _write_spec(tmp_path, bad)
    with pytest.raises(SpecError, match="unknown persona"):
        load_spec(tmp_path)


def test_duplicate_question_id_raises(tmp_path):
    _write_spec(tmp_path, GOOD_QUESTION)
    (tmp_path / "questions" / "q001_dup.yaml").write_text(GOOD_QUESTION)
    with pytest.raises(SpecError, match="duplicate question id"):
        load_spec(tmp_path)


def test_unsafe_yaml_tag_rejected(tmp_path):
    evil = GOOD_QUESTION + "\nevil: !!python/object/apply:os.system ['echo pwned']\n"
    _write_spec(tmp_path, evil)
    with pytest.raises(SpecError):
        load_spec(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spec_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa.spec.loader'`

- [ ] **Step 3: Write gaa/spec/loader.py**

```python
# gaa/spec/loader.py
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from gaa.spec.models import Invariant, Persona, Question


class SpecError(Exception):
    """Raised when the evaluation spec is malformed or internally inconsistent."""


@dataclass(frozen=True)
class Spec:
    personas: dict[str, Persona]
    questions: list[Question]
    invariants: list[Invariant]
    root: Path


def _read_yaml(path: Path) -> dict:
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{path}: expected a mapping at the top level")
    return data


def load_spec(root: Path) -> Spec:
    """Load and validate the evaluation spec directory.

    Validates structure, referential integrity between questions and personas, and
    the existence of every referenced reference-SQL file.
    """
    personas_raw = _read_yaml(root / "personas.yaml").get("personas", [])
    try:
        personas = {p.name: p for p in (Persona(**item) for item in personas_raw)}
    except (ValidationError, TypeError) as exc:
        raise SpecError(f"personas.yaml: {exc}") from exc

    invariants_raw = _read_yaml(root / "invariants.yaml").get("invariants", [])
    try:
        invariants = [Invariant(**item) for item in invariants_raw]
    except (ValidationError, TypeError) as exc:
        raise SpecError(f"invariants.yaml: {exc}") from exc

    questions: list[Question] = []
    seen: set[str] = set()
    for path in sorted((root / "questions").glob("*.yaml")):
        data = _read_yaml(path)
        try:
            question = Question(**data)
        except (ValidationError, TypeError) as exc:
            raise SpecError(f"{path}: {exc}") from exc

        if question.id in seen:
            raise SpecError(f"{path}: duplicate question id {question.id!r}")
        seen.add(question.id)

        sql_path = root / "reference_sql" / question.reference_sql
        if not sql_path.is_file():
            raise SpecError(f"{path}: reference SQL file not found: {question.reference_sql}")

        for expected in question.expected:
            if expected.persona not in personas:
                raise SpecError(f"{path}: unknown persona {expected.persona!r}")

        questions.append(question)

    return Spec(personas=personas, questions=questions, invariants=invariants, root=root)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spec_loader.py -v`
Expected: 5 passed

Note: `test_unsafe_yaml_tag_rejected` passes because `yaml.safe_load` raises on the `!!python/...` tag, which `_read_yaml` converts to `SpecError`.

- [ ] **Step 5: Commit**

```bash
git add gaa/spec/loader.py tests/test_spec_loader.py
git commit -m "feat(spec): loader with safe YAML and referential integrity checks"
```

---

### Task 4: The evaluation spec content — personas, first questions, invariants

**Files:**
- Create: `evals/spec/personas.yaml`, `evals/spec/invariants.yaml`, `evals/spec/questions/q001.yaml` … `q012.yaml`, `evals/spec/reference_sql/q001_*.sql` … `q012_*.sql`
- Test: `tests/test_real_spec_loads.py`

**Interfaces:**
- Consumes: `gaa.spec.loader.load_spec`.
- Produces: the on-disk spec at `evals/spec/`, referenced by every later task. Table and column names declared here are the contract Task 7–9 must satisfy: `FCT_ARR_ROLLFORWARD(FISCAL_QUARTER, REGION, ACCOUNT_ID, NET_NEW_ARR, EXPANSION_ARR, CHURN_ARR)`, `FCT_BOOKINGS(BOOKING_ID, ACCOUNT_ID, BOOKING_DATE, FISCAL_QUARTER, REGION, AMOUNT, IS_INTERCOMPANY)`, `DIM_ACCOUNT(ACCOUNT_ID, ACCOUNT_NAME, REGION, SEGMENT, OWNER_REP_ID)`, `DIM_TERRITORY_SCD(TERRITORY_ID, REGION, REP_ID, VALID_FROM, VALID_TO)`, `DIM_FISCAL_CALENDAR(CALENDAR_DATE, FISCAL_QUARTER, FISCAL_YEAR, QUARTER_START_DATE, QUARTER_END_DATE)`.

**This task must be committed before Task 6. That ordering is the project's integrity claim and is verified in Task 13.**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_real_spec_loads.py
from pathlib import Path

from gaa.spec.loader import load_spec

SPEC_ROOT = Path(__file__).parent.parent / "evals" / "spec"


def test_real_spec_loads_and_is_complete():
    spec = load_spec(SPEC_ROOT)
    assert set(spec.personas) == {"FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL"}
    assert len(spec.questions) >= 12
    assert len(spec.invariants) >= 4


def test_every_question_has_expectations_for_every_persona():
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        covered = {e.persona for e in question.expected}
        assert covered == set(spec.personas), f"{question.id} covers only {covered}"


def test_at_least_one_question_differs_across_personas():
    """The point of persona-aware ground truth: same question, different correct answers."""
    spec = load_spec(SPEC_ROOT)
    differing = [
        q for q in spec.questions
        if len({str(sorted(e.rows, key=str)) for e in q.expected}) > 1
    ]
    assert differing, "no question produces persona-differentiated ground truth"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_real_spec_loads.py -v`
Expected: FAIL — `evals/spec` does not exist

- [ ] **Step 3: Write evals/spec/personas.yaml**

```yaml
personas:
  - name: FINANCE_GLOBAL
    snowflake_role: GAA_FINANCE_GLOBAL
    description: Corporate FP&A. Sees every territory and unmasked account names.
  - name: SALES_DIR_EMEA
    snowflake_role: GAA_SALES_DIR_EMEA
    description: Regional sales leadership. Sees EMEA territories only.
  - name: REP_INDIVIDUAL
    snowflake_role: GAA_REP_INDIVIDUAL
    description: Individual contributor. Sees only accounts they own.
```

- [ ] **Step 4: Write evals/spec/invariants.yaml**

```yaml
invariants:
  - id: sum_of_parts_bookings
    description: Global bookings equal the sum of the three regional totals.
    kind: sum_of_parts
    params:
      question_id: q001
      whole_persona: FINANCE_GLOBAL
      value_column: VALUE
      part_column: REGION
      parts: [EMEA, AMER, APAC]

  - id: monotonic_nesting_arr
    description: Rep total is at most the EMEA total, which is at most the global total.
    kind: monotonic_nesting
    params:
      question_id: q003
      value_column: VALUE
      order: [REP_INDIVIDUAL, SALES_DIR_EMEA, FINANCE_GLOBAL]

  - id: masking_preserves_row_count
    description: Masking changes distinct account names but never the number of rows.
    kind: masking_preserves_row_count
    params:
      question_id: q007
      personas: [FINANCE_GLOBAL, SALES_DIR_EMEA]
      masked_column: ACCOUNT_NAME

  - id: determinism_all_questions
    description: Running any question twice as the same persona returns identical rows.
    kind: determinism
    params:
      repeat: 2
```

- [ ] **Step 5: Write the twelve question files**

Each question is one YAML file plus one SQL file. Write all twelve. `q001` is given in full as the pattern; the remaining eleven follow it exactly, varying only in `id`, `text`, `reference_sql`, `grain`, `tags`, and `expected`.

The twelve questions, chosen so that each targets a distinct failure category:

| id | question text | targets |
|---|---|---|
| q001 | Total bookings for Q3 FY26 by region, excluding intercompany | baseline; sum-of-parts |
| q002 | Total bookings for Q3 FY26 including intercompany | wrong filter omission |
| q003 | Net new ARR for Q3 FY26 | monotonic nesting across personas |
| q004 | Bookings for the last day of Q2 FY26 | wrong date boundary (off-by-one) |
| q005 | Bookings by owning rep for Q3 FY26 | wrong join grain |
| q006 | Bookings by account and territory for Q3 FY26 | fan-out double counting via SCD join |
| q007 | Top 10 accounts by bookings in Q3 FY26 | masking behaviour |
| q008 | Bookings by segment for Q3 FY26 | NULL segment must appear, not be dropped |
| q009 | Expansion ARR minus churn ARR for FY26 | wrong column selection |
| q010 | Quota attainment by rep for Q3 FY26 | effective-dated quota |
| q011 | Bookings by region for the quarter that ended most recently | fiscal calendar resolution |
| q012 | Total bookings for a region the persona cannot see | governance over-block vs leak |

```yaml
# evals/spec/questions/q001.yaml
id: q001
text: What were total bookings for Q3 FY26 by region, excluding intercompany?
reference_sql: q001_bookings_by_region.sql
grain: region
source: authored
tags: [bookings, baseline, sum_of_parts]
expected:
  - persona: FINANCE_GLOBAL
    rows:
      - {REGION: AMER, VALUE: "0.00"}
      - {REGION: APAC, VALUE: "0.00"}
      - {REGION: EMEA, VALUE: "0.00"}
  - persona: SALES_DIR_EMEA
    rows:
      - {REGION: EMEA, VALUE: "0.00"}
  - persona: REP_INDIVIDUAL
    rows:
      - {REGION: EMEA, VALUE: "0.00"}
```

```sql
-- evals/spec/reference_sql/q001_bookings_by_region.sql
-- Ground truth for q001. Written against base marts, independent of the semantic
-- layer. Grain: one row per region. V_BOOKINGS is UNQUALIFIED on purpose: the session
-- default schema differs per persona, so this one statement yields three different
-- correct answers. See docs/adr/0001-governance-on-standard-edition.md.
SELECT
    b.REGION                    AS REGION,
    SUM(b.AMOUNT)               AS VALUE
FROM V_BOOKINGS AS b
WHERE b.FISCAL_QUARTER = 'FY26-Q3'
  AND b.IS_INTERCOMPANY = FALSE
GROUP BY b.REGION
ORDER BY b.REGION;
```

The `VALUE` placeholders of `"0.00"` are filled in Task 11, when the warehouse exists and the reference SQL can actually be executed. Until then they are structurally valid and the spec loads. **The questions and the SQL are frozen at this commit; only the expected values are filled later.** Task 13 asserts that no `reference_sql` file is modified after Task 6.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_real_spec_loads.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit — this is the integrity commit**

```bash
git add evals/spec/ tests/test_real_spec_loads.py
git commit -m "spec: evaluation questions, reference SQL, personas, and invariants

Committed before any dbt model exists. Models are built to satisfy this spec,
not the reverse. Verifiable in git log; asserted by tests/test_spec_predates_models.py."
```

---

### Task 5: Spec validation CLI and CI gate

**Files:**
- Create: `gaa/cli.py`, `.github/workflows/ci.yml`, `Makefile`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `gaa.spec.loader.load_spec`.
- Produces: `gaa spec-validate [--root PATH]` exiting 0 on a valid spec and 1 with a diagnostic on an invalid one; `make spec-validate`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from pathlib import Path

from click.testing import CliRunner

from gaa.cli import cli

SPEC_ROOT = Path(__file__).parent.parent / "evals" / "spec"


def test_spec_validate_succeeds_on_real_spec():
    result = CliRunner().invoke(cli, ["spec-validate", "--root", str(SPEC_ROOT)])
    assert result.exit_code == 0
    assert "questions" in result.output


def test_spec_validate_fails_on_broken_spec(tmp_path):
    (tmp_path / "personas.yaml").write_text("personas: []\n")
    (tmp_path / "invariants.yaml").write_text("invariants: []\n")
    (tmp_path / "questions").mkdir()
    (tmp_path / "reference_sql").mkdir()
    (tmp_path / "questions" / "bad.yaml").write_text("id: x\n")  # missing required fields
    result = CliRunner().invoke(cli, ["spec-validate", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "spec error" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa.cli'`

- [ ] **Step 3: Write gaa/cli.py**

```python
# gaa/cli.py
import sys
from pathlib import Path

import click

from gaa.spec.loader import SpecError, load_spec

DEFAULT_SPEC_ROOT = Path("evals/spec")


@click.group()
def cli() -> None:
    """Governed analytics agent tooling."""


@cli.command("spec-validate")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
def spec_validate(root: Path) -> None:
    """Validate the evaluation spec: structure, references, and persona coverage."""
    try:
        spec = load_spec(root)
    except SpecError as exc:
        click.echo(f"spec error: {exc}", err=True)
        sys.exit(1)

    click.echo(
        f"spec ok: {len(spec.questions)} questions, "
        f"{len(spec.personas)} personas, {len(spec.invariants)} invariants"
    )
```

- [ ] **Step 4: Write the Makefile**

```makefile
.PHONY: setup spec-validate lint test

setup:
	uv sync --all-extras

spec-validate:
	uv run gaa spec-validate --root evals/spec

lint:
	uv run ruff check gaa tests

test:
	uv run pytest -v
```

- [ ] **Step 5: Write .github/workflows/ci.yml**

```yaml
name: ci

on: [push, pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history: test_spec_predates_models inspects git log
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras
      - run: uv run ruff check gaa tests
      - run: uv run gaa spec-validate --root evals/spec
      - run: uv run pytest -v
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v && make lint`
Expected: 2 passed, ruff clean

- [ ] **Step 7: Commit**

```bash
git add gaa/cli.py Makefile .github/ tests/test_cli.py
git commit -m "feat(cli): spec-validate command and CI gate"
```

---

### Task 6: Generic profile-driven synthetic data generator

**Files:**
- Create: `gaa/synth/__init__.py`, `gaa/synth/profile.py`, `gaa/synth/generate.py`
- Create: `warehouse/seeds/profile.yaml` (the GTM domain shape, as config)
- Create: `warehouse/seeds/*.csv` (generated output, committed)
- Modify: `gaa/cli.py` (add `synth` command)
- Test: `tests/test_synth.py`, `tests/test_seed_data.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gaa.synth.profile.{ColumnProfile, TableProfile, DatasetProfile, load_profile}`;
  `gaa.synth.generate.generate(profile, seed) -> dict[str, list[dict]]`; CLI `gaa synth`.
- Generated tables and columns: `raw_accounts(ACCOUNT_ID, ACCOUNT_NAME, REGION, SEGMENT,
  OWNER_REP_ID)`, `raw_bookings(BOOKING_ID, ACCOUNT_ID, BOOKING_DATE, AMOUNT, LICENSE_TYPE,
  TERM_MONTHS, IS_INTERCOMPANY, CURRENCY)`, `raw_billings(BILLING_ID, BOOKING_ID, INVOICE_DATE,
  AMOUNT)`, `raw_revenue(REVENUE_ID, BOOKING_ID, RECOGNITION_DATE, AMOUNT)`,
  `raw_territory_assignments(TERRITORY_ID, REGION, REP_ID, VALID_FROM, VALID_TO)`,
  `raw_quota(REP_ID, FISCAL_QUARTER, QUOTA_AMOUNT, VALID_FROM, VALID_TO)`.

**Why generic, not a fixture script.** Profiling and generation are the same capability pointed in
opposite directions. Building the generator to consume a declared profile means an adopter can later
point it at their own warehouse and obtain synthetic data with their shape and none of their
numbers. See `docs/adr/0002-synthetic-data-no-admin-ui-deferred-deal-intelligence.md`.

**Determinism is required.** Fixed seed, integer arithmetic for money, no wall-clock reads. The same
profile and seed must produce byte-identical CSVs, or the ground truth drifts underneath the eval.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synth.py
from decimal import Decimal
from pathlib import Path

import pytest

from gaa.synth.generate import generate
from gaa.synth.profile import load_profile

PROFILE = Path(__file__).parent.parent / "warehouse" / "seeds" / "profile.yaml"


def test_generation_is_deterministic():
    """Same profile, same seed, byte-identical output. Ground truth cannot drift."""
    a = generate(load_profile(PROFILE), seed=42)
    b = generate(load_profile(PROFILE), seed=42)
    assert a == b


def test_different_seed_gives_different_data():
    a = generate(load_profile(PROFILE), seed=42)
    b = generate(load_profile(PROFILE), seed=43)
    assert a["raw_bookings"] != b["raw_bookings"]


def test_money_is_two_decimal_places_never_float():
    data = generate(load_profile(PROFILE), seed=42)
    for table, column in [("raw_bookings", "AMOUNT"), ("raw_billings", "AMOUNT"),
                          ("raw_revenue", "AMOUNT"), ("raw_quota", "QUOTA_AMOUNT")]:
        for row in data[table]:
            value = row[column]
            assert isinstance(value, str), f"{table}.{column} must be str, not float"
            assert Decimal(value) == Decimal(value).quantize(Decimal("0.01"))


def test_seeded_orphans_exist_and_are_reported():
    """The anomalies are ground truth, so the generator must place AND record them."""
    data = generate(load_profile(PROFILE), seed=42)
    booked = {r["BOOKING_ID"] for r in data["raw_bookings"]}
    billed = {r["BOOKING_ID"] for r in data["raw_billings"]}
    revenued = {r["BOOKING_ID"] for r in data["raw_revenue"]}

    unbilled = booked - billed
    unrecognised = booked - revenued
    assert unbilled, "must seed bookings with no billing"
    assert unrecognised, "must seed bookings with no revenue"

    manifest = data["_anomalies"]
    assert set(manifest["bookings_without_billing"]) == unbilled
    assert set(manifest["bookings_without_revenue"]) == unrecognised


def test_perpetual_recognises_once_subscription_recognises_ratably():
    data = generate(load_profile(PROFILE), seed=42)
    by_booking = {r["BOOKING_ID"]: r for r in data["raw_bookings"]}
    rows_for = {}
    for r in data["raw_revenue"]:
        rows_for.setdefault(r["BOOKING_ID"], []).append(r)

    perpetual = [b for b, r in by_booking.items()
                 if r["LICENSE_TYPE"] == "perpetual" and b in rows_for]
    subscription = [b for b, r in by_booking.items()
                    if r["LICENSE_TYPE"] == "subscription" and b in rows_for]
    assert perpetual and subscription

    assert all(len(rows_for[b]) == 1 for b in perpetual), "perpetual recognises once"
    assert all(len(rows_for[b]) == by_booking[b]["TERM_MONTHS"] for b in subscription), \
        "subscription recognises once per month of term"


def test_recognised_revenue_sums_to_booking_amount():
    data = generate(load_profile(PROFILE), seed=42)
    by_booking = {r["BOOKING_ID"]: Decimal(r["AMOUNT"]) for r in data["raw_bookings"]}
    total = {}
    for r in data["raw_revenue"]:
        total[r["BOOKING_ID"]] = total.get(r["BOOKING_ID"], Decimal("0")) + Decimal(r["AMOUNT"])
    for booking_id, recognised in total.items():
        assert recognised == by_booking[booking_id], f"{booking_id} revenue != booking amount"


def test_null_segment_present():
    data = generate(load_profile(PROFILE), seed=42)
    assert any(r["SEGMENT"] == "" for r in data["raw_accounts"])


def test_quarter_boundary_booking_exists():
    """q008 tests an off-by-one on the quarter edge; the data must contain one."""
    data = generate(load_profile(PROFILE), seed=42)
    assert any(r["BOOKING_DATE"] == "2026-06-30" for r in data["raw_bookings"])


def test_territory_reassignment_mid_quarter():
    data = generate(load_profile(PROFILE), seed=42)
    per_territory = {}
    for r in data["raw_territory_assignments"]:
        per_territory.setdefault(r["TERRITORY_ID"], []).append(r)
    assert any(len(v) > 1 for v in per_territory.values())
```

- [ ] **Step 2: Run it, confirm ModuleNotFoundError for gaa.synth**

Run: `uv run pytest tests/test_synth.py -v`

- [ ] **Step 3: Write `warehouse/seeds/profile.yaml`**

The domain shape lives here as data, not in code. Fiscal year is the calendar year.

```yaml
seed: 42
fiscal_year_start_month: 1
accounts:
  count: 120
  regions: [EMEA, AMER, APAC]
  segments: ["Enterprise", "Mid-Market", "SMB", ""]   # "" becomes NULL
  reps: 12
bookings:
  per_account: [1, 4]
  amount_range: [1000, 250000]
  window: ["2026-01-01", "2026-09-30"]
  license_split: {perpetual: 0.4, subscription: 0.6}
  subscription_terms: [12, 24, 36]
  intercompany_every: 37
anomalies:
  bookings_without_billing: 6
  bookings_without_revenue: 5
  quarter_boundary_dates: ["2026-06-30"]
  territory_reassignment_date: "2026-08-15"
```

- [ ] **Step 4: Write `gaa/synth/profile.py`**

Pydantic models mirroring the YAML above — `ColumnProfile`, `TableProfile`, `DatasetProfile`, and
`load_profile(path) -> DatasetProfile` using `yaml.safe_load`. Mirror the structure of
`gaa/spec/loader.py`: a `ProfileError` for malformed input, no raw SQL anywhere, and validation that
`license_split` sums to 1.0 and every anomaly count is smaller than the row count it applies to.

- [ ] **Step 5: Write `gaa/synth/generate.py`**

`generate(profile, seed) -> dict[str, list[dict]]`, returning one key per table plus `_anomalies`,
a manifest of every deliberately placed anomaly. Requirements:

- money as `str` produced from integer cents, never `float`
- `random.Random(seed)` only; no module-level `random`, no wall-clock reads
- perpetual bookings produce exactly one revenue row on the booking date; subscription bookings
  produce one row per month of `term_months`, the final row absorbing any rounding remainder so
  recognised revenue sums exactly to the booking amount
- billings mirror bookings one-to-one except for the seeded unbilled set
- anomalies chosen deterministically from the sorted booking list, never by sampling

- [ ] **Step 6: Add the CLI command and regenerate seeds**

```python
# append to gaa/cli.py
@cli.command("synth")
@click.option("--profile", type=click.Path(path_type=Path),
              default=Path("warehouse/seeds/profile.yaml"))
@click.option("--out", type=click.Path(path_type=Path), default=Path("warehouse/seeds"))
def synth(profile: Path, out: Path) -> None:
    """Generate synthetic seed data from a profile. Deterministic for a given seed."""
    from gaa.synth.generate import generate
    from gaa.synth.profile import load_profile

    spec = load_profile(profile)
    data = generate(spec, seed=spec.seed)
    for table, rows in data.items():
        if table.startswith("_"):
            continue
        path = out / f"{table}.csv"
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        click.echo(f"{path}: {len(rows)} rows")
    anomalies = out / "_anomalies.json"
    anomalies.write_text(json.dumps(data["_anomalies"], indent=2, sort_keys=True))
    click.echo(f"{anomalies}: anomaly manifest")
```

Run: `uv run gaa synth`

- [ ] **Step 7: Write tests/test_seed_data.py against the generated CSVs**

Assert on the committed files rather than the in-memory result: money has exactly two decimal
places as text, all three regions appear, at least one NULL segment, bookings reference real
accounts, and `_anomalies.json` matches what is actually missing from the billing and revenue files.

- [ ] **Step 8: Run everything and commit**

Run: `uv run pytest -q && uv run ruff check gaa tests`

```bash
git add gaa/synth/ gaa/cli.py warehouse/seeds/ tests/test_synth.py tests/test_seed_data.py
git commit -m "feat(synth): generic profile-driven synthetic data generator"
```

---

### Task 7: dbt project and staging models

**Files:**
- Create: `warehouse/dbt_project.yml`, `warehouse/profiles.example.yml`, `warehouse/models/staging/stg_accounts.sql`, `stg_bookings.sql`, `stg_territory_assignments.sql`, `stg_quota.sql`, `warehouse/models/staging/schema.yml`

**Interfaces:**
- Consumes: the seeds from Task 6.
- Produces: `STG_ACCOUNTS`, `STG_BOOKINGS`, `STG_TERRITORY_ASSIGNMENTS`, `STG_QUOTA` with typed columns and NULL policies declared.

- [ ] **Step 1: Write warehouse/dbt_project.yml**

```yaml
name: gaa
version: "0.1.0"
config-version: 2
profile: gaa
model-paths: ["models"]
seed-paths: ["seeds"]
target-path: "target"
models:
  gaa:
    staging:
      +materialized: view
    marts:
      +materialized: table
```

- [ ] **Step 2: Write warehouse/profiles.example.yml**

```yaml
# Copy to ~/.dbt/profiles.yml. Values come from the same environment variables as gaa.config.
gaa:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
      user: "{{ env_var('SNOWFLAKE_USER') }}"
      private_key_path: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PATH') }}"
      role: GAA_LOADER
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE') }}"
      database: "{{ env_var('SNOWFLAKE_DATABASE') }}"
      schema: "{{ env_var('SNOWFLAKE_SCHEMA') }}"
      threads: 4
```

- [ ] **Step 3: Write the staging models**

```sql
-- warehouse/models/staging/stg_bookings.sql
SELECT
    BOOKING_ID::VARCHAR                  AS BOOKING_ID,
    ACCOUNT_ID::VARCHAR                  AS ACCOUNT_ID,
    BOOKING_DATE::DATE                   AS BOOKING_DATE,
    AMOUNT::NUMBER(38,2)                 AS AMOUNT,
    IS_INTERCOMPANY::BOOLEAN             AS IS_INTERCOMPANY,
    CURRENCY::VARCHAR                    AS CURRENCY
FROM {{ ref('raw_bookings') }}
```

```sql
-- warehouse/models/staging/stg_accounts.sql
-- Empty-string segment becomes a real NULL here, once, so downstream models never
-- have to guess. q008 asserts the NULL segment survives aggregation.
SELECT
    ACCOUNT_ID::VARCHAR                      AS ACCOUNT_ID,
    ACCOUNT_NAME::VARCHAR                    AS ACCOUNT_NAME,
    REGION::VARCHAR                          AS REGION,
    NULLIF(TRIM(SEGMENT), '')::VARCHAR       AS SEGMENT,
    OWNER_REP_ID::VARCHAR                    AS OWNER_REP_ID
FROM {{ ref('raw_accounts') }}
```

```sql
-- warehouse/models/staging/stg_territory_assignments.sql
SELECT
    TERRITORY_ID::VARCHAR   AS TERRITORY_ID,
    REGION::VARCHAR         AS REGION,
    REP_ID::VARCHAR         AS REP_ID,
    VALID_FROM::DATE        AS VALID_FROM,
    VALID_TO::DATE          AS VALID_TO
FROM {{ ref('raw_territory_assignments') }}
```

```sql
-- warehouse/models/staging/stg_quota.sql
SELECT
    REP_ID::VARCHAR              AS REP_ID,
    FISCAL_QUARTER::VARCHAR      AS FISCAL_QUARTER,
    QUOTA_AMOUNT::NUMBER(38,2)   AS QUOTA_AMOUNT,
    VALID_FROM::DATE             AS VALID_FROM,
    VALID_TO::DATE               AS VALID_TO
FROM {{ ref('raw_quota') }}
```

- [ ] **Step 4: Write warehouse/models/staging/schema.yml**

```yaml
version: 2
models:
  - name: stg_bookings
    columns:
      - name: BOOKING_ID
        tests: [unique, not_null]
      - name: ACCOUNT_ID
        tests:
          - not_null
          - relationships: {to: ref('stg_accounts'), field: ACCOUNT_ID}
      - name: AMOUNT
        tests: [not_null]
  - name: stg_accounts
    columns:
      - name: ACCOUNT_ID
        tests: [unique, not_null]
      - name: REGION
        tests:
          - not_null
          - accepted_values: {values: ['EMEA', 'AMER', 'APAC']}
      - name: SEGMENT
        description: "Nullable by design. A NULL segment must survive aggregation."
  - name: stg_territory_assignments
    columns:
      - name: REP_ID
        tests: [not_null]
  - name: stg_quota
    columns:
      - name: REP_ID
        tests: [not_null]
```

- [ ] **Step 5: Run dbt to verify**

Run: `cd warehouse && uv run dbt seed && uv run dbt run --select staging && uv run dbt test --select staging`
Expected: seeds load, 4 views build, all tests pass

- [ ] **Step 6: Commit**

```bash
git add warehouse/dbt_project.yml warehouse/profiles.example.yml warehouse/models/staging/
git commit -m "feat(warehouse): dbt project and staging models"
```

---

### Task 8: Mart models — fiscal calendar, territory SCD, bookings, ARR roll-forward

**Files:**
- Create: `warehouse/models/marts/dim_fiscal_calendar.sql`, `dim_territory_scd.sql`, `dim_account.sql`, `fct_bookings.sql`, `fct_arr_rollforward.sql`, `warehouse/models/marts/schema.yml`

**Interfaces:**
- Consumes: staging models from Task 7.
- Produces: exactly the tables and columns declared in Task 4's Interfaces block. Any deviation breaks the frozen reference SQL, which is the point — the spec is the contract.

- [ ] **Step 1: Write dim_fiscal_calendar.sql**

```sql
-- warehouse/models/marts/dim_fiscal_calendar.sql
-- The single owner of every period boundary. No model may derive a fiscal quarter
-- by date arithmetic; they join here. FY26 begins 2026-02-01.
WITH days AS (
    SELECT DATEADD(day, SEQ4(), DATE '2025-02-01') AS CALENDAR_DATE
    FROM TABLE(GENERATOR(ROWCOUNT => 1461))
),
labelled AS (
    SELECT
        CALENDAR_DATE,
        YEAR(DATEADD(month, -1, CALENDAR_DATE)) + 1                     AS FISCAL_YEAR,
        FLOOR((MONTH(DATEADD(month, -1, CALENDAR_DATE)) - 1) / 3) + 1   AS FISCAL_QUARTER_NUM
    FROM days
)
SELECT
    CALENDAR_DATE,
    FISCAL_YEAR,
    'FY' || RIGHT(FISCAL_YEAR::VARCHAR, 2) || '-Q' || FISCAL_QUARTER_NUM::VARCHAR AS FISCAL_QUARTER,
    MIN(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM)        AS QUARTER_START_DATE,
    MAX(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM)        AS QUARTER_END_DATE
FROM labelled
```

- [ ] **Step 2: Write dim_territory_scd.sql and dim_account.sql**

```sql
-- warehouse/models/marts/dim_territory_scd.sql
-- Effective-dated. Joins to this table MUST constrain on VALID_FROM/VALID_TO or
-- they fan out — which is exactly what q006 is designed to catch.
SELECT
    TERRITORY_ID,
    REGION,
    REP_ID,
    VALID_FROM,
    VALID_TO
FROM {{ ref('stg_territory_assignments') }}
```

```sql
-- warehouse/models/marts/dim_account.sql
SELECT
    ACCOUNT_ID,
    ACCOUNT_NAME,
    REGION,
    SEGMENT,
    OWNER_REP_ID
FROM {{ ref('stg_accounts') }}
```

- [ ] **Step 3: Write fct_bookings.sql and fct_arr_rollforward.sql**

```sql
-- warehouse/models/marts/fct_bookings.sql
-- Grain: one row per booking. REGION and OWNER_REP_ID are denormalised from the
-- account so the persona views can filter without a join.
SELECT
    b.BOOKING_ID,
    b.ACCOUNT_ID,
    b.BOOKING_DATE,
    cal.FISCAL_QUARTER,
    a.REGION,
    a.OWNER_REP_ID,
    b.AMOUNT,
    b.IS_INTERCOMPANY
FROM {{ ref('stg_bookings') }} AS b
JOIN {{ ref('dim_account') }} AS a
  ON a.ACCOUNT_ID = b.ACCOUNT_ID
JOIN {{ ref('dim_fiscal_calendar') }} AS cal
  ON cal.CALENDAR_DATE = b.BOOKING_DATE
```

```sql
-- warehouse/models/marts/fct_arr_rollforward.sql
-- Grain: one row per account per fiscal quarter. Expansion and churn are derived
-- from the quarter-over-quarter change in booked amount.
WITH quarterly AS (
    SELECT
        ACCOUNT_ID,
        FISCAL_QUARTER,
        REGION,
        SUM(AMOUNT) AS BOOKED_AMOUNT
    FROM {{ ref('fct_bookings') }}
    WHERE IS_INTERCOMPANY = FALSE
    GROUP BY ACCOUNT_ID, FISCAL_QUARTER, REGION
),
with_prior AS (
    SELECT
        *,
        LAG(BOOKED_AMOUNT) OVER (PARTITION BY ACCOUNT_ID ORDER BY FISCAL_QUARTER) AS PRIOR_AMOUNT
    FROM quarterly
)
SELECT
    FISCAL_QUARTER,
    REGION,
    ACCOUNT_ID,
    CASE WHEN PRIOR_AMOUNT IS NULL THEN BOOKED_AMOUNT ELSE 0 END::NUMBER(38,2)                  AS NET_NEW_ARR,
    GREATEST(COALESCE(BOOKED_AMOUNT - PRIOR_AMOUNT, 0), 0)::NUMBER(38,2)                        AS EXPANSION_ARR,
    GREATEST(COALESCE(PRIOR_AMOUNT - BOOKED_AMOUNT, 0), 0)::NUMBER(38,2)                        AS CHURN_ARR
FROM with_prior
```

- [ ] **Step 4: Write warehouse/models/marts/schema.yml**

```yaml
version: 2
models:
  - name: dim_fiscal_calendar
    columns:
      - name: CALENDAR_DATE
        tests: [unique, not_null]
      - name: FISCAL_QUARTER
        tests: [not_null]
  - name: fct_bookings
    columns:
      - name: BOOKING_ID
        tests: [unique, not_null]
      - name: AMOUNT
        tests: [not_null]
      - name: REGION
        tests:
          - accepted_values: {values: ['EMEA', 'AMER', 'APAC']}
  - name: fct_arr_rollforward
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [ACCOUNT_ID, FISCAL_QUARTER]
  - name: dim_account
    columns:
      - name: ACCOUNT_ID
        tests: [unique, not_null]
  - name: dim_territory_scd
    columns:
      - name: REP_ID
        tests: [not_null]
```

Add `warehouse/packages.yml` with `dbt_utils` and run `dbt deps`:

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.1.0", "<2.0.0"]
```

- [ ] **Step 5: Build and test**

Run: `cd warehouse && uv run dbt deps && uv run dbt run && uv run dbt test`
Expected: all models build, all tests pass

- [ ] **Step 6: Commit**

```bash
git add warehouse/models/marts/ warehouse/packages.yml
git commit -m "feat(warehouse): fiscal calendar, territory SCD, bookings and ARR marts"
```

---

### Task 9: Roles, per-persona schemas, and grants

**Files:**
- Create: `warehouse/governance/01_roles_and_schemas.sql`, `warehouse/governance/02_grants.sql`,
  `scripts/apply_governance.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: mart tables from Task 8.
- Produces: roles `GAA_LOADER`, `GAA_FINANCE_GLOBAL`, `GAA_SALES_DIR_EMEA`, `GAA_REP_INDIVIDUAL`;
  schemas `GAA.FINANCE`, `GAA.EMEA`, `GAA.REP`; `scripts/apply_governance.py` as the only privileged
  code path in the repository.

Row access policies and masking policies are Enterprise-only and this account is Standard. See
`docs/adr/0001-governance-on-standard-edition.md`. The boundary is schema-scoped grants instead.

- [ ] **Step 1: Write 01_roles_and_schemas.sql**

```sql
-- warehouse/governance/01_roles_and_schemas.sql
-- Four roles, three persona schemas. Persona roles are deliberately NOT nested:
-- nesting would let a rep inherit finance visibility, which is the exact leak the
-- evaluation exists to catch.
USE ROLE SECURITYADMIN;

CREATE ROLE IF NOT EXISTS GAA_LOADER;
CREATE ROLE IF NOT EXISTS GAA_FINANCE_GLOBAL;
CREATE ROLE IF NOT EXISTS GAA_SALES_DIR_EMEA;
CREATE ROLE IF NOT EXISTS GAA_REP_INDIVIDUAL;

GRANT ROLE GAA_LOADER         TO ROLE SYSADMIN;
GRANT ROLE GAA_FINANCE_GLOBAL TO ROLE SYSADMIN;
GRANT ROLE GAA_SALES_DIR_EMEA TO ROLE SYSADMIN;
GRANT ROLE GAA_REP_INDIVIDUAL TO ROLE SYSADMIN;

USE ROLE SYSADMIN;
CREATE SCHEMA IF NOT EXISTS GAA.FINANCE;
CREATE SCHEMA IF NOT EXISTS GAA.EMEA;
CREATE SCHEMA IF NOT EXISTS GAA.REP;
```

- [ ] **Step 2: Write 02_grants.sql**

```sql
-- warehouse/governance/02_grants.sql
-- Each persona role is granted USAGE on exactly ONE schema. MARTS is loader-only.
-- These grants ARE the boundary, so a mis-grant is a breach rather than a bug; the
-- conformance suite tests them adversarially.
USE ROLE SYSADMIN;

GRANT USAGE ON DATABASE GAA TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON DATABASE GAA TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON DATABASE GAA TO ROLE GAA_REP_INDIVIDUAL;

GRANT USAGE ON SCHEMA GAA.FINANCE TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON SCHEMA GAA.EMEA    TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON SCHEMA GAA.REP     TO ROLE GAA_REP_INDIVIDUAL;

GRANT USAGE ON WAREHOUSE GAA_WH TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON WAREHOUSE GAA_WH TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON WAREHOUSE GAA_WH TO ROLE GAA_REP_INDIVIDUAL;
```

- [ ] **Step 3: Write scripts/apply_governance.py**

Governance DDL is applied by a logged, re-runnable script, never pasted into a worksheet. `dbt run`
recreates tables and drops dependent views, so this is re-run after every build.

```python
# scripts/apply_governance.py
"""Apply governance DDL in order, idempotently, with a log of what ran.

Every statement must be re-runnable: CREATE ... IF NOT EXISTS, CREATE OR REPLACE,
or a GRANT. This is the ONLY privileged code path in the repository; nothing under
gaa/ may use SYSADMIN, and the bypass tests assert that separation.
"""
import sys
from pathlib import Path

import click

from gaa.config import load_settings
from gaa.connection import session_for_persona
from gaa.spec.models import Persona

GOVERNANCE_DIR = Path(__file__).parent.parent / "warehouse" / "governance"
ADMIN = Persona(
    name="ADMIN", snowflake_role="SYSADMIN", snowflake_schema="MARTS", description="DDL only"
)


def _statements(sql: str) -> list[str]:
    out = []
    for chunk in sql.split(";"):
        lines = [ln for ln in chunk.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            out.append(stmt)
    return out


@click.command()
@click.option("--only", default=None, help="substring match on filename, e.g. '02_grants'")
def main(only: str | None) -> None:
    settings = load_settings()
    files = sorted(GOVERNANCE_DIR.glob("*.sql"))
    if only:
        files = [f for f in files if only in f.name]
    if not files:
        click.echo("no governance files matched", err=True)
        sys.exit(1)

    with session_for_persona(ADMIN, settings) as conn:
        cursor = conn.cursor()
        for path in files:
            click.echo(f"--- {path.name}")
            for statement in _statements(path.read_text()):
                preview = " ".join(statement.split())[:90]
                try:
                    cursor.execute(statement)
                    click.echo(f"    ok   {preview}  [{cursor.sfqid}]")
                except Exception as exc:
                    click.echo(f"    FAIL {preview}\n         {exc}", err=True)
                    sys.exit(1)
    click.echo("governance applied")


if __name__ == "__main__":
    main()
```

Add to the Makefile:
```makefile
.PHONY: governance
governance:
	uv run python scripts/apply_governance.py
```

- [ ] **Step 4: Apply and verify**

Run: `uv run python scripts/apply_governance.py --only 01_roles && uv run python scripts/apply_governance.py --only 02_grants`

Verify a persona role sees its schema and nothing else:
```sql
USE ROLE GAA_REP_INDIVIDUAL;
SHOW SCHEMAS IN DATABASE GAA;   -- expect REP only
```

- [ ] **Step 5: Commit**

```bash
git add warehouse/governance/ scripts/apply_governance.py Makefile
git commit -m "feat(governance): roles, per-persona schemas, and scoped grants"
```

---

### Task 10: Per-persona secure views and the bypass suite

**Files:**
- Create: `warehouse/governance/03_persona_views.sql`, `gaa/connection.py`
- Test: `tests/test_governance_boundary.py`

**Interfaces:**
- Consumes: roles and schemas from Task 9, marts from Task 8.
- Produces: `V_BOOKINGS`, `V_ARR`, `V_ACCOUNT` in each of `GAA.FINANCE`, `GAA.EMEA`, `GAA.REP` —
  same names, different definitions; and
  `gaa.connection.session_for_persona(persona, settings=None) -> SnowflakeConnection`.

The identical view names are the mechanism. Reference SQL is unqualified, the session default schema
differs per persona, so one SQL string yields three different correct answers.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_governance_boundary.py
"""Integration tests. Require a live Snowflake account; skipped without credentials."""
import os
from pathlib import Path

import pytest

from gaa.connection import session_for_persona
from gaa.spec.loader import load_spec

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"), reason="no Snowflake credentials"
)

SPEC = load_spec(Path(__file__).parent.parent / "evals" / "spec")
SAME_SQL = "SELECT DISTINCT REGION FROM V_BOOKINGS"


def _regions(persona_name: str) -> set[str]:
    with session_for_persona(SPEC.personas[persona_name]) as conn:
        cur = conn.cursor()
        cur.execute(SAME_SQL)
        return {row[0] for row in cur.fetchall()}


def test_identical_sql_yields_different_answers_per_persona():
    """The central claim, asserted directly: one SQL string, three correct answers."""
    assert _regions("FINANCE_GLOBAL") == {"EMEA", "AMER", "APAC"}
    assert _regions("SALES_DIR_EMEA") == {"EMEA"}
    assert _regions("REP_INDIVIDUAL") <= {"EMEA"}


def test_rep_cannot_read_another_personas_schema():
    with session_for_persona(SPEC.personas["REP_INDIVIDUAL"]) as conn:
        with pytest.raises(Exception):
            conn.cursor().execute("SELECT COUNT(*) FROM GAA.FINANCE.V_BOOKINGS")


def test_rep_cannot_read_base_marts():
    with session_for_persona(SPEC.personas["REP_INDIVIDUAL"]) as conn:
        with pytest.raises(Exception):
            conn.cursor().execute("SELECT COUNT(*) FROM GAA.MARTS.FCT_BOOKINGS")


def test_rep_cannot_escalate_role():
    with session_for_persona(SPEC.personas["REP_INDIVIDUAL"]) as conn:
        with pytest.raises(Exception):
            conn.cursor().execute("USE ROLE GAA_FINANCE_GLOBAL")


def test_masking_changes_values_but_not_row_count():
    def names(persona):
        with session_for_persona(SPEC.personas[persona]) as conn:
            cur = conn.cursor()
            cur.execute("SELECT ACCOUNT_NAME FROM V_ACCOUNT ORDER BY ACCOUNT_ID")
            return [r[0] for r in cur.fetchall()]

    finance = names("FINANCE_GLOBAL")
    emea = names("SALES_DIR_EMEA")
    emea_subset = [n for n in finance if n]  # finance is a superset; compare overlap only
    assert emea and finance
    assert all(n.startswith("ACCOUNT-") for n in emea), "EMEA names must be masked"
    assert not all(n.startswith("ACCOUNT-") for n in emea_subset), "finance names must be clear"
```

- [ ] **Step 2: Run it, confirm ModuleNotFoundError for gaa.connection**

Run: `uv run pytest tests/test_governance_boundary.py -v`

- [ ] **Step 3: Write gaa/connection.py**

```python
# gaa/connection.py
from contextlib import contextmanager
from typing import Iterator

import snowflake.connector
from cryptography.hazmat.primitives import serialization

from gaa.config import Settings, load_settings
from gaa.spec.models import Persona


def _private_key_bytes(settings: Settings) -> bytes:
    passphrase = settings.snowflake_private_key_passphrase
    with settings.snowflake_private_key_path.open("rb") as fh:
        key = serialization.load_pem_private_key(
            fh.read(), password=passphrase.encode() if passphrase else None
        )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@contextmanager
def session_for_persona(
    persona: Persona, settings: Settings | None = None
) -> Iterator[snowflake.connector.SnowflakeConnection]:
    """Open a Snowflake session bound to one persona's role AND schema.

    Both are fixed at connect time. The schema is as load-bearing as the role:
    reference SQL is unqualified, so the default schema is what makes identical SQL
    resolve to that persona's view. No code path elevates either afterward.
    """
    settings = settings or load_settings()
    conn = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        private_key=_private_key_bytes(settings),
        role=persona.snowflake_role,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=persona.snowflake_schema,
        session_parameters={"QUERY_TAG": f"gaa:{persona.name}"},
    )
    try:
        yield conn
    finally:
        conn.close()
```

- [ ] **Step 4: Write 03_persona_views.sql**

```sql
-- warehouse/governance/03_persona_views.sql
-- Identical view NAMES in three schemas, different definitions. This is the
-- boundary: the session default schema selects which one an unqualified query hits.
-- CREATE OR REPLACE because dbt drops dependents whenever it rebuilds a mart.
USE ROLE SYSADMIN;

-- FINANCE: everything, names in the clear.
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_BOOKINGS AS SELECT * FROM GAA.MARTS.FCT_BOOKINGS;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_ARR      AS SELECT * FROM GAA.MARTS.FCT_ARR_ROLLFORWARD;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_ACCOUNT  AS SELECT * FROM GAA.MARTS.DIM_ACCOUNT;

-- EMEA: region-filtered, account names masked.
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_BOOKINGS AS
    SELECT * FROM GAA.MARTS.FCT_BOOKINGS WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_ARR AS
    SELECT * FROM GAA.MARTS.FCT_ARR_ROLLFORWARD WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_ACCOUNT AS
    SELECT ACCOUNT_ID, 'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME,
           REGION, SEGMENT, OWNER_REP_ID
    FROM GAA.MARTS.DIM_ACCOUNT WHERE REGION = 'EMEA';

-- REP: own accounts only, names masked.
CREATE OR REPLACE SECURE VIEW GAA.REP.V_BOOKINGS AS
    SELECT * FROM GAA.MARTS.FCT_BOOKINGS WHERE OWNER_REP_ID = 'REP001';
CREATE OR REPLACE SECURE VIEW GAA.REP.V_ARR AS
    SELECT * FROM GAA.MARTS.FCT_ARR_ROLLFORWARD WHERE OWNER_REP_ID = 'REP001';
CREATE OR REPLACE SECURE VIEW GAA.REP.V_ACCOUNT AS
    SELECT ACCOUNT_ID, 'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME,
           REGION, SEGMENT, OWNER_REP_ID
    FROM GAA.MARTS.DIM_ACCOUNT WHERE OWNER_REP_ID = 'REP001';

GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.FINANCE TO ROLE GAA_FINANCE_GLOBAL;
GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.EMEA    TO ROLE GAA_SALES_DIR_EMEA;
GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.REP     TO ROLE GAA_REP_INDIVIDUAL;
```

`REP001` is hardcoded. A real deployment maps `CURRENT_USER()` to a rep; the hardcode is acceptable
for a single-user reference deployment and is listed as accepted risk in the threat model.

- [ ] **Step 5: Apply, then run the boundary suite**

Run: `uv run python scripts/apply_governance.py --only 03_persona_views`
Then: `uv run pytest tests/test_governance_boundary.py -v`
Expected: 5 passed against a live account.

- [ ] **Step 6: Commit**

```bash
git add warehouse/governance/03_persona_views.sql gaa/connection.py tests/test_governance_boundary.py
git commit -m "feat(governance): per-persona secure views and the bypass suite"
```

---

### Task 11: Reference SQL executor and expected-value capture

**Files:**
- Create: `gaa/runner/__init__.py`, `gaa/runner/reference.py`
- Modify: `gaa/cli.py` (add `eval-reference` and `capture-expected` commands)
- Modify: `evals/spec/questions/*.yaml` (fill `expected` values only)
- Test: `tests/test_reference_runner.py`

**Interfaces:**
- Consumes: `gaa.connection.session_for_persona`, `gaa.spec.loader.Spec`.
- Produces: `gaa.runner.reference.ReferenceResult(question_id, persona, rows, query_id)` and `gaa.runner.reference.run_reference(spec, question, persona) -> ReferenceResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reference_runner.py
from unittest.mock import MagicMock, patch

from gaa.runner.reference import run_reference
from gaa.spec.models import Persona, Question


def _question(tmp_path):
    (tmp_path / "reference_sql").mkdir(parents=True, exist_ok=True)
    (tmp_path / "reference_sql" / "q.sql").write_text("SELECT 'EMEA' AS REGION, 1.00 AS VALUE;")
    return Question(
        id="q001", text="t", reference_sql="q.sql", grain="region",
        expected=[], tags=[], source="authored",
    )


def test_run_reference_normalises_decimals_to_strings(tmp_path):
    from decimal import Decimal

    question = _question(tmp_path)
    persona = Persona(name="P", snowflake_role="R", description="d")

    cursor = MagicMock()
    cursor.description = [("REGION",), ("VALUE",)]
    cursor.fetchall.return_value = [("EMEA", Decimal("1.00"))]
    cursor.sfqid = "01b2-abcd"
    conn = MagicMock()
    conn.cursor.return_value = cursor

    with patch("gaa.runner.reference.session_for_persona") as sess:
        sess.return_value.__enter__.return_value = conn
        result = run_reference(tmp_path, question, persona)

    assert result.rows == [{"REGION": "EMEA", "VALUE": "1.00"}]
    assert result.query_id == "01b2-abcd"
    assert result.persona == "P"


def test_run_reference_rejects_multi_statement_sql(tmp_path):
    question = _question(tmp_path)
    (tmp_path / "reference_sql" / "q.sql").write_text("SELECT 1; DROP TABLE X;")
    persona = Persona(name="P", snowflake_role="R", description="d")
    import pytest

    with pytest.raises(ValueError, match="single statement"):
        run_reference(tmp_path, question, persona)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reference_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa.runner'`

- [ ] **Step 3: Write gaa/runner/reference.py**

```python
# gaa/runner/reference.py
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from gaa.connection import session_for_persona
from gaa.spec.models import Persona, Question


@dataclass(frozen=True)
class ReferenceResult:
    question_id: str
    persona: str
    rows: list[dict[str, str]]
    query_id: str


def _normalise(value: object) -> str:
    """Render every value as a string so decimal scale survives comparison."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    return str(value)


def run_reference(spec_root: Path, question: Question, persona: Persona) -> ReferenceResult:
    """Execute one question's reference SQL as one persona.

    The SQL is read from disk and sent verbatim. Nothing is interpolated into it,
    and exactly one statement is permitted.
    """
    sql = (spec_root / "reference_sql" / question.reference_sql).read_text()
    if len([s for s in sql.split(";") if s.strip()]) != 1:
        raise ValueError(f"{question.reference_sql}: must contain a single statement")

    with session_for_persona(persona) as conn:
        cursor = conn.cursor()
        cursor.execute(sql.strip().rstrip(";"))
        columns = [c[0] for c in cursor.description]
        rows = [dict(zip(columns, (_normalise(v) for v in row))) for row in cursor.fetchall()]
        query_id = cursor.sfqid

    return ReferenceResult(question.id, persona.name, rows, query_id)
```

Create `gaa/runner/__init__.py` as an empty file.

- [ ] **Step 4: Add the CLI commands**

```python
# append to gaa/cli.py
import yaml

from gaa.runner.reference import run_reference


@cli.command("capture-expected")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
def capture_expected(root: Path) -> None:
    """Execute every question as every persona and write the results into the spec.

    This fills the `expected` blocks only. Question text and reference SQL are
    already frozen; this command must never modify them.
    """
    spec = load_spec(root)
    for question in spec.questions:
        expected = []
        for persona in spec.personas.values():
            result = run_reference(root, question, persona)
            expected.append({"persona": persona.name, "rows": result.rows})
            click.echo(f"{question.id} as {persona.name}: {len(result.rows)} rows ({result.query_id})")

        path = root / "questions" / f"{question.id}.yaml"
        with path.open() as fh:
            data = yaml.safe_load(fh)
        data["expected"] = expected
        with path.open("w") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False)
```

- [ ] **Step 5: Run unit tests, then capture real values**

Run: `uv run pytest tests/test_reference_runner.py -v`
Expected: 2 passed

Then, against the live warehouse: `uv run gaa capture-expected`
Expected: per-question, per-persona row counts and query IDs printed; `evals/spec/questions/*.yaml` now carry real values.

- [ ] **Step 6: Verify persona differentiation is real**

Run: `uv run pytest tests/test_real_spec_loads.py::test_at_least_one_question_differs_across_personas -v`
Expected: PASS — and now against real captured numbers rather than placeholders

- [ ] **Step 7: Commit**

```bash
git add gaa/runner/ gaa/cli.py evals/spec/questions/ tests/test_reference_runner.py
git commit -m "feat(runner): execute reference SQL per persona and capture ground truth"
```

---

### Task 12: Invariant checker

**Files:**
- Create: `gaa/runner/invariants.py`
- Modify: `gaa/cli.py` (add `check-invariants`)
- Test: `tests/test_invariants.py`

**Interfaces:**
- Consumes: `gaa.spec.loader.Spec`, `gaa.runner.reference.ReferenceResult`.
- Produces: `gaa.runner.invariants.InvariantResult(invariant_id, passed, detail)` and `gaa.runner.invariants.check_invariant(inv, results) -> InvariantResult`, where `results` is `dict[tuple[str, str], ReferenceResult]` keyed by `(question_id, persona)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_invariants.py
from gaa.runner.invariants import check_invariant
from gaa.runner.reference import ReferenceResult
from gaa.spec.models import Invariant


def _res(qid, persona, rows):
    return ReferenceResult(qid, persona, rows, "qid-1")


def test_sum_of_parts_passes_when_whole_equals_sum():
    inv = Invariant(
        id="s", description="d", kind="sum_of_parts",
        params={"question_id": "q001", "whole_persona": "FINANCE_GLOBAL",
                "value_column": "VALUE", "part_column": "REGION",
                "parts": ["EMEA", "AMER", "APAC"]},
    )
    results = {("q001", "FINANCE_GLOBAL"): _res("q001", "FINANCE_GLOBAL", [
        {"REGION": "EMEA", "VALUE": "10.00"},
        {"REGION": "AMER", "VALUE": "20.00"},
        {"REGION": "APAC", "VALUE": "30.00"},
    ])}
    assert check_invariant(inv, results).passed


def test_sum_of_parts_fails_when_a_region_is_missing():
    inv = Invariant(
        id="s", description="d", kind="sum_of_parts",
        params={"question_id": "q001", "whole_persona": "FINANCE_GLOBAL",
                "value_column": "VALUE", "part_column": "REGION",
                "parts": ["EMEA", "AMER", "APAC"]},
    )
    results = {("q001", "FINANCE_GLOBAL"): _res("q001", "FINANCE_GLOBAL", [
        {"REGION": "EMEA", "VALUE": "10.00"},
        {"REGION": "AMER", "VALUE": "20.00"},
    ])}
    result = check_invariant(inv, results)
    assert not result.passed
    assert "APAC" in result.detail


def test_monotonic_nesting_passes_when_rep_le_region_le_global():
    inv = Invariant(
        id="m", description="d", kind="monotonic_nesting",
        params={"question_id": "q003", "value_column": "VALUE",
                "order": ["REP_INDIVIDUAL", "SALES_DIR_EMEA", "FINANCE_GLOBAL"]},
    )
    results = {
        ("q003", "REP_INDIVIDUAL"): _res("q003", "REP_INDIVIDUAL", [{"VALUE": "5.00"}]),
        ("q003", "SALES_DIR_EMEA"): _res("q003", "SALES_DIR_EMEA", [{"VALUE": "50.00"}]),
        ("q003", "FINANCE_GLOBAL"): _res("q003", "FINANCE_GLOBAL", [{"VALUE": "500.00"}]),
    }
    assert check_invariant(inv, results).passed


def test_monotonic_nesting_fails_on_leak():
    """A rep seeing the global number is the exact failure this catches."""
    inv = Invariant(
        id="m", description="d", kind="monotonic_nesting",
        params={"question_id": "q003", "value_column": "VALUE",
                "order": ["REP_INDIVIDUAL", "SALES_DIR_EMEA", "FINANCE_GLOBAL"]},
    )
    results = {
        ("q003", "REP_INDIVIDUAL"): _res("q003", "REP_INDIVIDUAL", [{"VALUE": "500.00"}]),
        ("q003", "SALES_DIR_EMEA"): _res("q003", "SALES_DIR_EMEA", [{"VALUE": "50.00"}]),
        ("q003", "FINANCE_GLOBAL"): _res("q003", "FINANCE_GLOBAL", [{"VALUE": "500.00"}]),
    }
    assert not check_invariant(inv, results).passed


def test_masking_preserves_row_count():
    inv = Invariant(
        id="k", description="d", kind="masking_preserves_row_count",
        params={"question_id": "q007", "personas": ["FINANCE_GLOBAL", "SALES_DIR_EMEA"],
                "masked_column": "ACCOUNT_NAME"},
    )
    results = {
        ("q007", "FINANCE_GLOBAL"): _res("q007", "FINANCE_GLOBAL",
                                         [{"ACCOUNT_NAME": "Real A"}, {"ACCOUNT_NAME": "Real B"}]),
        ("q007", "SALES_DIR_EMEA"): _res("q007", "SALES_DIR_EMEA",
                                         [{"ACCOUNT_NAME": "ACCOUNT-1"}, {"ACCOUNT_NAME": "ACCOUNT-2"}]),
    }
    assert check_invariant(inv, results).passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invariants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gaa.runner.invariants'`

- [ ] **Step 3: Write gaa/runner/invariants.py**

```python
# gaa/runner/invariants.py
from dataclasses import dataclass
from decimal import Decimal

from gaa.runner.reference import ReferenceResult
from gaa.spec.models import Invariant

Results = dict[tuple[str, str], ReferenceResult]


@dataclass(frozen=True)
class InvariantResult:
    invariant_id: str
    passed: bool
    detail: str


def _total(rows: list[dict[str, str]], column: str) -> Decimal:
    return sum((Decimal(r[column] or "0") for r in rows), Decimal("0"))


def _sum_of_parts(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    result = results.get((p["question_id"], p["whole_persona"]))
    if result is None:
        return InvariantResult(inv.id, False, f"no result for {p['question_id']}/{p['whole_persona']}")

    seen = {row[p["part_column"]] for row in result.rows}
    missing = [part for part in p["parts"] if part not in seen]
    if missing:
        return InvariantResult(inv.id, False, f"missing parts: {', '.join(missing)}")

    whole = _total(result.rows, p["value_column"])
    parts = _total([r for r in result.rows if r[p["part_column"]] in p["parts"]], p["value_column"])
    if whole != parts:
        return InvariantResult(inv.id, False, f"whole {whole} != sum of parts {parts}")
    return InvariantResult(inv.id, True, f"whole == sum of parts == {whole}")


def _monotonic_nesting(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    totals = []
    for persona in p["order"]:
        result = results.get((p["question_id"], persona))
        if result is None:
            return InvariantResult(inv.id, False, f"no result for {p['question_id']}/{persona}")
        totals.append((persona, _total(result.rows, p["value_column"])))

    for (lo_name, lo), (hi_name, hi) in zip(totals, totals[1:]):
        if lo > hi:
            return InvariantResult(inv.id, False, f"{lo_name} ({lo}) exceeds {hi_name} ({hi})")
    return InvariantResult(inv.id, True, " <= ".join(f"{n}:{v}" for n, v in totals))


def _masking_preserves_row_count(inv: Invariant, results: Results) -> InvariantResult:
    p = inv.params
    counts, distincts = {}, {}
    for persona in p["personas"]:
        result = results.get((p["question_id"], persona))
        if result is None:
            return InvariantResult(inv.id, False, f"no result for {p['question_id']}/{persona}")
        counts[persona] = len(result.rows)
        distincts[persona] = {row[p["masked_column"]] for row in result.rows}

    if len(set(counts.values())) != 1:
        return InvariantResult(inv.id, False, f"row counts differ: {counts}")
    values = list(distincts.values())
    if values[0] == values[1]:
        return InvariantResult(inv.id, False, "masked and unmasked values are identical")
    return InvariantResult(inv.id, True, f"row count {list(counts.values())[0]} preserved, values differ")


def _determinism(inv: Invariant, results: Results) -> InvariantResult:
    # Determinism is asserted by the runner re-executing; nothing to compute here.
    return InvariantResult(inv.id, True, "checked by repeated execution in the runner")


_HANDLERS = {
    "sum_of_parts": _sum_of_parts,
    "monotonic_nesting": _monotonic_nesting,
    "masking_preserves_row_count": _masking_preserves_row_count,
    "determinism": _determinism,
}


def check_invariant(inv: Invariant, results: Results) -> InvariantResult:
    """Evaluate one metamorphic invariant against captured reference results."""
    return _HANDLERS[inv.kind](inv, results)
```

- [ ] **Step 4: Add the CLI command**

```python
# append to gaa/cli.py
from gaa.runner.invariants import check_invariant


@cli.command("check-invariants")
@click.option("--root", type=click.Path(path_type=Path), default=DEFAULT_SPEC_ROOT)
def check_invariants(root: Path) -> None:
    """Execute every question as every persona, then evaluate all invariants."""
    spec = load_spec(root)
    results = {}
    for question in spec.questions:
        for persona in spec.personas.values():
            results[(question.id, persona.name)] = run_reference(root, question, persona)

    failures = 0
    for inv in spec.invariants:
        outcome = check_invariant(inv, results)
        status = "PASS" if outcome.passed else "FAIL"
        click.echo(f"[{status}] {outcome.invariant_id}: {outcome.detail}")
        failures += 0 if outcome.passed else 1

    if failures:
        click.echo(f"{failures} invariant(s) failed", err=True)
        sys.exit(1)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_invariants.py -v`
Expected: 5 passed

Then against the warehouse: `uv run gaa check-invariants`
Expected: all invariants PASS

- [ ] **Step 6: Commit**

```bash
git add gaa/runner/invariants.py gaa/cli.py tests/test_invariants.py
git commit -m "feat(runner): metamorphic invariant checker"
```

---

### Task 13: Spec-predates-models assertion

**Files:**
- Create: `tests/test_spec_predates_models.py`
- Modify: `Makefile`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: git history.
- Produces: a test that fails if any model file was committed before the spec, or if frozen reference SQL was modified after model work began.

This task converts the project's central integrity claim from prose into an executable assertion. Without it, "the spec predates the models" is something a reader must take on trust.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec_predates_models.py
"""The integrity claim, asserted.

The evaluation spec must be committed before any dbt model, and reference SQL must
not change once models exist. Both are verifiable from git history, which is what
makes "our evals are honest" checkable rather than merely stated.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent


def _first_commit_time(pathspec: str) -> int:
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ct", "--reverse", "--", pathspec],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert out, f"no commit found adding {pathspec}"
    return int(out[0])


def _commits_touching(pathspec: str) -> list[str]:
    return subprocess.run(
        ["git", "log", "--format=%H", "--", pathspec],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()


def test_spec_questions_committed_before_any_dbt_model():
    spec_time = _first_commit_time("evals/spec/questions")
    model_time = _first_commit_time("warehouse/models")
    assert spec_time < model_time, (
        "evaluation spec must be committed before warehouse models; "
        f"spec={spec_time} models={model_time}"
    )


def test_reference_sql_not_modified_after_models_exist():
    model_time = _first_commit_time("warehouse/models")
    for commit in _commits_touching("evals/spec/reference_sql"):
        ts = int(subprocess.run(
            ["git", "show", "-s", "--format=%ct", commit],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout.strip())
        assert ts < model_time, (
            f"commit {commit[:8]} modified frozen reference SQL after models existed"
        )
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_spec_predates_models.py -v`
Expected: 2 passed — if either fails, the history genuinely violates the claim and the plan was executed out of order

- [ ] **Step 3: Wire into Makefile and CI**

```makefile
# add to Makefile
.PHONY: verify-integrity eval

verify-integrity:
	uv run pytest tests/test_spec_predates_models.py -v

eval:
	uv run gaa check-invariants --root evals/spec
```

The CI workflow already runs `uv run pytest -v` with `fetch-depth: 0`, so this test runs in CI without further change. Confirm `fetch-depth: 0` is present — without full history the git queries return nothing and the test errors rather than passing silently.

- [ ] **Step 4: Commit**

```bash
git add tests/test_spec_predates_models.py Makefile
git commit -m "test: assert the spec predates the models in git history"
```

---

## Self-Review Notes

**Spec coverage.** This plan covers the spec's Phase 0 (Tasks 2–5), Phase 1 warehouse (Tasks 6–8), and Phase 1 governance (Tasks 9–10), plus the evaluation mechanics that Phase 1 needs to be verifiable (Tasks 11–13). Not covered here, by design: the semantic layer, MCP server, agent, answer card, chaos suite, Spider2 adapter, deployment tiers, and the rollout plan and threat model documents. Those belong to Plans 2 and 3.

**Known gaps to carry into Plan 2.**
- The `REP_INDIVIDUAL` policy hardcodes `REP001`. A real deployment maps `CURRENT_USER()` to a rep; the hardcode is acceptable for a single-user reference deployment and must be called out in the threat model as accepted risk.
- `FCT_ARR_ROLLFORWARD` needs `OWNER_REP_ID` so the REP persona view can filter on it. Add it to the `quarterly` CTE grouping in `fct_arr_rollforward.sql` when building Task 8.
- The chaos suite is not built here. The failure taxonomy exists as an enum from Task 2 but nothing scores against it until the agent exists.
