from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every value comes from the environment."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    snowflake_account: str = Field(alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(alias="SNOWFLAKE_USER")
    snowflake_private_key_path: Path = Field(alias="SNOWFLAKE_PRIVATE_KEY_PATH")
    snowflake_private_key_passphrase: str | None = Field(
        default=None, alias="SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"
    )
    snowflake_warehouse: str = Field(alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(alias="SNOWFLAKE_SCHEMA")


def load_settings() -> Settings:
    """Load settings, raising ValueError when a required variable is absent."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pydantic raises ValidationError, a subclass of ValueError
        raise ValueError(f"invalid or missing configuration: {exc}") from exc
