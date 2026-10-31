"""Reusable settings loaded only when the caller creates an instance."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._config import DEFAULT_API_VERSION, DEFAULT_TIMEOUT, APIVersion, RequestTimeout, Token


class BotSettings(BaseSettings):
    """Read VK_* variables, with optional explicit dotenv loading and subclass fields.

    No instance is created at import time. Pass ``_env_file=Path(".env")`` to opt into
    dotenv loading. Pass values explicitly to override their environment counterparts.
    """

    model_config = SettingsConfigDict(
        env_prefix="VK_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    token: Token = Field(repr=False)
    group_id: int = Field(gt=0)
    api_version: APIVersion = DEFAULT_API_VERSION
    timeout: RequestTimeout = DEFAULT_TIMEOUT
    polling_wait: int = Field(default=25, ge=1, le=90)
