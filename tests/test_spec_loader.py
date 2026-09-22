import pytest

from gaa.spec.loader import SpecError, load_spec


def _write_spec(root, question_yaml, sql_files=("q001_x.sql",)):
    (root / "questions").mkdir(parents=True)
    (root / "reference_sql").mkdir(parents=True)
    (root / "personas.yaml").write_text(
        "personas:\n"
        "  - name: FINANCE_GLOBAL\n"
        "    snowflake_role: GAA_FINANCE_GLOBAL\n"
        "    snowflake_schema: FINANCE\n"
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


def test_missing_personas_file_raises_spec_error(tmp_path):
    """A partial spec directory must fail as a SpecError, not an unhandled OSError.

    spec-validate reports SpecError cleanly and exits 1; anything else surfaces as a
    traceback, which reads as a tool bug rather than as the spec problem it is.
    """
    (tmp_path / "questions").mkdir()
    (tmp_path / "reference_sql").mkdir()
    with pytest.raises(SpecError, match="required spec file is missing"):
        load_spec(tmp_path)
