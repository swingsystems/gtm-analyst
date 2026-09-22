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
