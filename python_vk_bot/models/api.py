"""API envelope and Long Poll response boundaries."""

from pydantic import Field, JsonValue, SecretStr, field_validator

from .base import VKModel


class APIErrorData(VKModel):
    error_code: int
    error_msg: str = Field(repr=False)


class APIEnvelope(VKModel):
    response: JsonValue = None
    error: APIErrorData | None = Field(default=None, repr=False)


class LongPollServer(VKModel):
    key: SecretStr
    server: str
    ts: str

    @field_validator("ts", mode="before")
    @classmethod
    def normalize_ts(cls, value: object) -> object:
        return str(value) if type(value) is int else value


class LongPollResponse(VKModel):
    failed: int | None = None
    ts: str | None = None
    updates: list[dict[str, JsonValue]] | None = None

    @field_validator("ts", mode="before")
    @classmethod
    def normalize_ts(cls, value: object) -> object:
        return str(value) if type(value) is int else value
