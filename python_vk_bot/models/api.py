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


class UploadServer(VKModel):
    upload_url: str = Field(min_length=1, repr=False)


class PhotoUpload(VKModel):
    server: int = Field(strict=True)
    photo: str = Field(min_length=1, repr=False)
    hash: str = Field(min_length=1, repr=False)


class DocumentUpload(VKModel):
    file: str = Field(min_length=1, repr=False)


class MessageDeleteError(VKModel):
    code: int = Field(strict=True)


class MessageDeleteResult(VKModel):
    peer_id: int | None = None
    message_id: int | None = None
    conversation_message_id: int | None = None
    response: int | None = Field(default=None, strict=True, ge=0, le=1)
    error: MessageDeleteError | None = Field(default=None, repr=False)
