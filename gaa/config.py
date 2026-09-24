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
