"""The committed spec must load, cover every persona, and target real categories."""
from collections import Counter
from pathlib import Path

from gtm_analyst.spec.loader import load_spec
from gtm_analyst.spec.sql import sql_statements
from gtm_analyst.spec.taxonomy import FailureCategory

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


def test_expected_values_were_captured_from_the_warehouse():
    """Ground truth is executed, never authored. Hand-written numbers would be a
    guess wearing the costume of a measurement.

    Empty results are legitimate for two questions -- q007 is deliberately
    unanswerable, and q012 asks restricted personas for a region they cannot see
    -- so emptiness alone is not a defect. A question where NO persona returned
    anything means the capture silently failed.
    """
    spec = load_spec(SPEC_ROOT)
    deliberately_empty = {"q007"}
    for question in spec.questions:
        assert len(question.expected) == 3, question.id
        if question.id in deliberately_empty:
            assert all(e.rows == [] for e in question.expected), question.id
            continue
        assert any(e.rows for e in question.expected), f"{question.id} captured nothing"


def test_captured_results_respect_the_persona_hierarchy():
    """rep <= EMEA <= global in row count, for every question that returns rows.

    The monotonic_nesting invariant applied to the captured spec itself. A rep
    seeing more rows than the regional director would mean the boundary leaked
    while the numbers still looked entirely plausible.
    """
    spec = load_spec(SPEC_ROOT)
    for question in spec.questions:
        # q009 is a per-persona TOP 10: each returns its own ten, and ranking is
        # not a subset relation, so the nesting does not apply.
        if question.id == "q009":
            continue
        counts = {e.persona: len(e.rows) for e in question.expected}
        rep, emea, glob = (counts["REP_INDIVIDUAL"], counts["SALES_DIR_EMEA"],
                           counts["FINANCE_GLOBAL"])
        assert rep <= emea <= glob, f"{question.id}: rep={rep} emea={emea} global={glob}"
