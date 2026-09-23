"""The committed spec must load, cover every persona, and target real categories."""
from collections import Counter
from pathlib import Path

from gaa.spec.loader import load_spec
from gaa.spec.sql import sql_statements
from gaa.spec.taxonomy import FailureCategory

SPEC_ROOT = Path(__file__).parent.parent / "evals" / "spec"


def test_real_spec_loads_and_is_complete():
    spec = load_spec(SPEC_ROOT)
    assert set(spec.personas) == {"FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL"}
    assert len(spec.questions) == 12
    assert len(spec.invariants) == 4


def test_every_question_has_an_entry_for_every_persona():
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        covered = {e.persona for e in question.expected}
        assert covered == set(spec.personas), f"{question.id} covers only {covered}"


def test_every_persona_declares_a_distinct_schema():
    """The schema is what makes identical SQL resolve per persona. Duplicates
    would silently collapse two personas into one."""
    spec = load_spec(SPEC_ROOT)
    schemas = [p.snowflake_schema for p in spec.personas.values()]
    assert len(set(schemas)) == len(schemas), f"duplicate schemas: {schemas}"


def test_reference_sql_is_unqualified():
    """Qualified names would defeat the per-persona schema resolution outright."""
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        sql = (SPEC_ROOT / "reference_sql" / question.reference_sql).read_text().upper()
        body = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
        assert "GAA." not in body, f"{question.reference_sql} uses a qualified name"


def test_each_reference_sql_is_a_single_statement():
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        sql = (SPEC_ROOT / "reference_sql" / question.reference_sql).read_text()
        assert len(sql_statements(sql)) == 1, question.reference_sql


def test_targeted_categories_are_real_and_broadly_covered():
    spec = load_spec(SPEC_ROOT)
    targeted = Counter(q.targets for q in spec.questions)
    for category in targeted:
        assert isinstance(category, FailureCategory)
    untargeted = {c for c in FailureCategory} - set(targeted)
    # governance_leak is cross-cutting: scored on every question, targeted by none.
    assert untargeted == {FailureCategory.GOVERNANCE_LEAK}, f"untargeted: {untargeted}"


def test_expected_values_are_still_empty():
    """Ground truth is captured from the warehouse in task 11, not authored here.
    Hand-written numbers would be a guess wearing the costume of a measurement."""
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        for expected in question.expected:
            assert expected.rows == [], f"{question.id}/{expected.persona} pre-filled"
