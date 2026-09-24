import pytest
from pydantic import ValidationError

from gaa.spec.models import ExpectedResult, Invariant, Persona, Question
from gaa.spec.taxonomy import FailureCategory


def test_persona_requires_role_and_schema():
    p = Persona(
        name="FINANCE_GLOBAL",
        snowflake_role="GAA_FINANCE_GLOBAL",
        snowflake_schema="FINANCE",
        description="FP&A",
    )
    assert p.snowflake_role == "GAA_FINANCE_GLOBAL"
    assert p.snowflake_schema == "FINANCE"


def test_persona_without_schema_is_rejected():
    """The schema is load-bearing: it is what makes identical SQL resolve per persona."""
    with pytest.raises(ValidationError):
        Persona(name="X", snowflake_role="R", description="d")


def test_question_rejects_inline_sql_field():
    """Contracts are metadata only. reference_sql names a FILE, never SQL text."""
    with pytest.raises(ValidationError):
        Question(
            id="q001",
            text="Net new ARR for Q3 FY26 by region",
            reference_sql="SELECT * FROM fct_arr_rollforward",
            grain="region",
            expected=[],
            tags=["arr"],
            source="authored",
            targets="wrong_column",
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
        targets="wrong_column",
    )
    assert q.reference_sql.endswith(".sql")
    assert q.expected[0].persona == "FINANCE_GLOBAL"


def test_question_source_must_be_known():
    with pytest.raises(ValidationError):
        Question(
            id="q002", text="x", reference_sql="q002.sql", grain="region",
            expected=[], tags=[], source="invented", targets="wrong_column",
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
    assert FailureCategory.ORPHANS_DROPPED.value == "orphans_dropped"
    assert len(list(FailureCategory)) == 9


def test_question_requires_a_target_category():
    """Every question exists to probe one failure category. Untargeted questions
    accumulate without anyone noticing they test nothing."""
    with pytest.raises(ValidationError):
        Question(
            id="q", text="t", reference_sql="q.sql", grain="g",
            expected=[], tags=[], source="authored",
        )


def test_question_rejects_unknown_fields():
    """extra='forbid': a typo'd key must fail loudly, not be silently ignored."""
    with pytest.raises(ValidationError):
        Question(
            id="q", text="t", reference_sql="q.sql", grain="g", expected=[],
            tags=[], source="authored", targets="wrong_column", targetz="oops",
        )


def test_spec_personas_default_to_their_own_service_user():
    """Spec personas connect as a single-role service user; operational
    identities built in code opt out explicitly."""
    p = Persona(name="X", snowflake_role="R", snowflake_schema="S", description="d")
    assert p.service_user is True
    admin = Persona(name="ADMIN", snowflake_role="ACCOUNTADMIN", snowflake_schema="MARTS",
                    description="d", service_user=False)
    assert admin.service_user is False
