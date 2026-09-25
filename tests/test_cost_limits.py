"""Nothing capped what an agent could spend, and it showed.

This project's own experiment was halted by an Anthropic spending limit -- the
same class of problem from the other side. On the warehouse side a pathological
question can scan large tables repeatedly, and an agent that retries is an agent
that retries expensively.

Three caps, in increasing order of bluntness: a statement timeout, a row cap on
what comes back, and a Snowflake resource monitor on the warehouse itself.
"""
import pytest

from gaa.config import Settings
from gaa.connection import session_parameters_for
from gaa.spec.models import Persona

PERSONA = Persona(
    name="REP_INDIVIDUAL", snowflake_role="GAA_REP_INDIVIDUAL",
    snowflake_schema="REP", description="test",
)


def _settings(**over) -> Settings:
    base = {
        "SNOWFLAKE_ACCOUNT": "a", "SNOWFLAKE_USER": "u",
        "SNOWFLAKE_PRIVATE_KEY_PATH": "/dev/null", "SNOWFLAKE_WAREHOUSE": "w",
        "SNOWFLAKE_DATABASE": "GAA", "SNOWFLAKE_SCHEMA": "MARTS",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_a_statement_timeout_is_always_set() -> None:
    """Without one, a runaway scan bills until Snowflake's account default --
    which on many accounts is two days."""
    params = session_parameters_for(PERSONA, _settings())
    assert int(params["STATEMENT_TIMEOUT_IN_SECONDS"]) > 0


def test_the_timeout_is_configurable_but_cannot_be_disabled() -> None:
    """Zero means 'no limit' to Snowflake. Accepting it from configuration
    would let an env var silently remove the cap."""
    params = session_parameters_for(PERSONA, _settings(GAA_STATEMENT_TIMEOUT_SECONDS="45"))
    assert params["STATEMENT_TIMEOUT_IN_SECONDS"] == "45"
    with pytest.raises(ValueError, match="timeout"):
        _settings(GAA_STATEMENT_TIMEOUT_SECONDS="0")


def test_the_query_tag_still_identifies_the_persona() -> None:
    """Adding caps must not cost the attribution that makes spend traceable."""
    assert session_parameters_for(PERSONA, _settings())["QUERY_TAG"] == "gaa:REP_INDIVIDUAL"


def test_a_row_cap_exists_and_is_positive() -> None:
    assert _settings().gaa_max_rows > 0


def test_the_row_cap_refuses_a_nonsense_value() -> None:
    with pytest.raises(ValueError, match="max_rows"):
        _settings(GAA_MAX_ROWS="0")


class _FakeCursor:
    """Returns `total` rows, honouring fetchmany's size like the real one."""

    def __init__(self, total: int):
        self._rows = [(i,) for i in range(total)]
        self._at = 0

    def fetchmany(self, size: int):
        chunk = self._rows[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


def test_a_result_under_the_cap_is_not_flagged_truncated(monkeypatch) -> None:
    from gaa.mcp import tools

    monkeypatch.setattr(tools, "load_settings", lambda: _settings(GAA_MAX_ROWS="10"))
    rows, truncated = tools._fetch_capped(_FakeCursor(10), ["N"])
    assert len(rows) == 10
    assert truncated is False, "a result exactly at the cap is complete, not truncated"


def test_a_result_over_the_cap_is_flagged_and_cut(monkeypatch) -> None:
    """The +1 fetch is what distinguishes 'hit the cap' from 'that was all'.
    Without it a truncated answer is indistinguishable from a complete one --
    the same failure as a silent partial answer from a restricted persona."""
    from gaa.mcp import tools

    monkeypatch.setattr(tools, "load_settings", lambda: _settings(GAA_MAX_ROWS="10"))
    rows, truncated = tools._fetch_capped(_FakeCursor(500), ["N"])
    assert len(rows) == 10
    assert truncated is True


def test_the_cap_never_returns_more_than_asked(monkeypatch) -> None:
    """The extra row is for detection only and must not reach the caller."""
    from gaa.mcp import tools

    monkeypatch.setattr(tools, "load_settings", lambda: _settings(GAA_MAX_ROWS="3"))
    rows, _ = tools._fetch_capped(_FakeCursor(9), ["N"])
    assert [r["N"] for r in rows] == ["0", "1", "2"]
