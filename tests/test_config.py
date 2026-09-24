
import pytest

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
    # The operator's real environment may be loaded; these tests must not read it.
    monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", raising=False)
    monkeypatch.delenv("SNOWFLAKE_SERVICE_USER_PREFIX", raising=False)

    settings = load_settings()

    assert settings.snowflake_account == "acct123"
    assert settings.snowflake_private_key_path == key
    assert settings.snowflake_private_key_passphrase is None


def test_load_settings_missing_required_var_raises(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
    monkeypatch.delenv("SNOWFLAKE_USER", raising=False)
    with pytest.raises(ValueError):
        load_settings()


def test_empty_env_value_is_treated_as_unset(monkeypatch, tmp_path):
    """A blank line in .env arrives as "" not absent. Treating that as a real
    value would mean decrypting an unencrypted key with an empty passphrase."""
    key = tmp_path / "k.p8"
    key.write_text("x")
    for name, value in [("SNOWFLAKE_ACCOUNT", "a"), ("SNOWFLAKE_USER", "u"),
                        ("SNOWFLAKE_PRIVATE_KEY_PATH", str(key)),
                        ("SNOWFLAKE_WAREHOUSE", "w"), ("SNOWFLAKE_DATABASE", "d"),
                        ("SNOWFLAKE_SCHEMA", "s"),
                        ("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", ""),
                        ("SNOWFLAKE_SERVICE_USER_PREFIX", "")]:
        monkeypatch.setenv(name, value)
    settings = load_settings()
    assert settings.snowflake_private_key_passphrase is None
    assert settings.snowflake_service_user_prefix is None
