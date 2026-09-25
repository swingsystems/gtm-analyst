from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every value comes from the environment."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    snowflake_account: str = Field(alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(alias="SNOWFLAKE_USER")
    # When set, each persona connects as "<prefix><PERSONA_NAME>" instead of the
    # operator. Those service users hold exactly one role each, which is what
    # makes the boundary real -- see gaa.connection.user_for_persona.
    snowflake_service_user_prefix: str | None = Field(
        default=None, alias="SNOWFLAKE_SERVICE_USER_PREFIX"
    )
    snowflake_private_key_path: Path = Field(alias="SNOWFLAKE_PRIVATE_KEY_PATH")
    snowflake_private_key_passphrase: str | None = Field(
        default=None, alias="SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"
    )
    snowflake_warehouse: str = Field(alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(alias="SNOWFLAKE_SCHEMA")

    # Cost caps. Nothing bounded agent spend before these existed, and this
    # project's own experiment was halted by a spending limit -- the same class
    # of problem from the other side.
    gaa_statement_timeout_seconds: int = Field(default=120,
                                               alias="GAA_STATEMENT_TIMEOUT_SECONDS")
    gaa_max_rows: int = Field(default=5000, alias="GAA_MAX_ROWS")
    gaa_credit_quota: int = Field(default=50, alias="GAA_CREDIT_QUOTA")

    @field_validator("gaa_statement_timeout_seconds")
    @classmethod
    def _timeout_cannot_be_disabled(cls, value: int) -> int:
        """Snowflake reads 0 as "no limit". Accepting it from configuration
        would let one env var silently remove the cap, which is exactly how a
        cap stops existing without anyone deciding to remove it."""
        if value <= 0:
            raise ValueError("statement timeout must be positive; 0 means no limit")
        return value

    @field_validator("gaa_max_rows")
    @classmethod
    def _row_cap_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("gaa_max_rows must be positive")
        return value


    @field_validator("snowflake_private_key_passphrase", "snowflake_service_user_prefix",
                     mode="before")
    @classmethod
    def _empty_string_is_unset(cls, value: str | None) -> str | None:
        """An unset variable in a .env file arrives as "" rather than absent.
        Treating that as a real value would mean trying to decrypt an unencrypted
        key with an empty passphrase, or prefixing usernames with nothing."""
        return value or None


def load_settings() -> Settings:
    """Load settings, raising ValueError when a required variable is absent."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic raises ValidationError, a subclass of ValueError
        raise ValueError(f"invalid or missing configuration: {exc}") from exc
