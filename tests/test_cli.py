from pathlib import Path

from click.testing import CliRunner

from gtm_analyst.cli import cli

SPEC_ROOT = Path(__file__).parent.parent / "evals" / "spec"


def test_spec_validate_succeeds_on_real_spec():
    result = CliRunner().invoke(cli, ["spec-validate", "--root", str(SPEC_ROOT)])
    assert result.exit_code == 0
    assert "12 questions" in result.output


def test_spec_validate_fails_on_broken_spec(tmp_path):
    (tmp_path / "personas.yaml").write_text("personas: []\n")
    (tmp_path / "invariants.yaml").write_text("invariants: []\n")
    (tmp_path / "questions").mkdir()
    (tmp_path / "reference_sql").mkdir()
    (tmp_path / "questions" / "bad.yaml").write_text("id: x\n")
    result = CliRunner().invoke(cli, ["spec-validate", "--root", str(tmp_path)])
    assert result.exit_code == 1
    assert "spec error" in result.output.lower()


def test_spec_validate_reports_missing_directory_cleanly(tmp_path):
    """Pointing it at the wrong directory is the most likely first mistake.
    It must say so, not emit a traceback."""
    result = CliRunner().invoke(cli, ["spec-validate", "--root", str(tmp_path / "nope")])
    assert result.exit_code == 1
    assert "spec error" in result.output.lower()
