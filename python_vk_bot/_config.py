"""Shared constraints for explicit configuration and environment-backed settings."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr

DEFAULT_API_VERSION = "5.199"
DEFAULT_TIMEOUT = 40.0

type Token = Annotated[SecretStr, Field(min_length=1)]
type APIVersion = Annotated[str, Field(pattern=r"^\d+\.\d+$")]
type RequestTimeout = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class TransportConfig(BaseModel):
    """Explicit transport values; never read environment variables or files."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    token: Token = Field(repr=False)
    api_version: APIVersion = DEFAULT_API_VERSION
    timeout: RequestTimeout = DEFAULT_TIMEOUT
