"""The integrity claim, asserted against git history.

The evaluation spec must have been committed before any data model existed, and
the reference SQL must not have changed once models arrived. Both are verifiable
with `git log`, which is what turns "these evaluations are honest" from a claim
a reader must trust into one they can check in about thirty seconds.

If either assertion fails, the history genuinely violates the claim. It cannot
be repaired by rewriting history -- rewriting is precisely the thing the history
exists to disprove.
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


def _first_added(pathspec: str) -> int:
    """Unix timestamp of the commit that first ADDED anything under pathspec."""
    out = _git("log", "--diff-filter=A", "--format=%ct", "--reverse", "--", pathspec).split()
    assert out, f"no commit found adding {pathspec}"
    return int(out[0])


def _commits_touching(pathspec: str) -> list[str]:
    return _git("log", "--format=%H", "--", pathspec).split()


def _committed_at(sha: str) -> int:
    return int(_git("show", "-s", "--format=%ct", sha).strip())


@pytest.fixture(scope="module", autouse=True)
def _requires_full_history():
    """A shallow clone makes every query below return nothing, and the
    assertions would pass vacuously -- the worst possible outcome for a test
    whose entire job is to be hard to satisfy."""
    if (REPO / ".git" / "shallow").exists():
        pytest.fail("shallow clone: fetch full history before asserting integrity")


def test_evaluation_spec_was_committed_before_any_data_model():
    spec_at = _first_added("evals/spec/questions")
    models_at = _first_added("warehouse/models")
    assert spec_at < models_at, (
        "the evaluation spec must predate the models it evaluates; "
        f"spec added at {spec_at}, models at {models_at}"
    )


def test_reference_sql_was_never_touched_after_models_existed():
    """Expected values are captured later and that is by design. The QUESTIONS
    and the SQL defining their ground truth are frozen at the spec commit."""
    models_at = _first_added("warehouse/models")
    for sha in _commits_touching("evals/spec/reference_sql"):
        assert _committed_at(sha) < models_at, (
            f"commit {sha[:8]} modified frozen reference SQL after models existed"
        )


def test_reference_sql_landed_in_exactly_one_commit():
    """Ground truth authored across several commits would allow a definition to
    be quietly revised while still technically predating the models."""
    shas = _commits_touching("evals/spec/reference_sql")
    assert len(shas) == 1, f"reference SQL spread across {len(shas)} commits: {shas}"
