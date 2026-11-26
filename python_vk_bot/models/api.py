"""API envelope and Long Poll response boundaries."""

from __future__ import annotations

from typing import Optional, Union

from pydantic import Field, JsonValue, SecretStr, field_validator

from .base import VKModel


class APIErrorData(VKModel):
    error_code: int
    error_msg: str = Field(repr=False)


class APIEnvelope(VKModel):
    response: JsonValue = None
    error: Optional[APIErrorData] = Field(default=None, repr=False)


class LongPollServer(VKModel):
    key: SecretStr
    server: str
    ts: str

    @field_validator("ts", mode="before")
    @classmethod
    def normalize_ts(cls, value: object) -> object:
        return str(value) if type(value) is int else value


class LongPollResponse(VKModel):
    failed: Optional[int] = None
    ts: Optional[str] = None
    updates: Optional[list[dict[str, JsonValue]]] = None

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


class MessageSendResult(VKModel):
    """Identifiers of one sent message; a global ID is not always available."""

    peer_id: int = Field(strict=True)
    message_id: Optional[int] = Field(strict=True, gt=0)
    conversation_message_id: int = Field(strict=True, gt=0)

    @field_validator("peer_id")
    @classmethod
    def validate_peer_id(cls, value: int) -> int:
        if value == 0:
            raise ValueError("peer_id must be nonzero")
        return value


class _MessageSendError(VKModel):
    code: int = Field(strict=True, gt=0)


class _MessageSendResponse(VKModel):
    """Recipient errors may carry zero or omitted message identifiers."""

    peer_id: int = Field(strict=True)
    message_id: Optional[int] = Field(default=None, strict=True, ge=0)
    conversation_message_id: Optional[int] = Field(default=None, strict=True, ge=0)
    error: Optional[_MessageSendError] = Field(default=None, repr=False)


class MessageDeleteError(VKModel):
    code: int = Field(strict=True)


class MessageDeleteResult(VKModel):
    peer_id: Union[int, None] = None
    message_id: Union[int, None] = None
    conversation_message_id: Union[int, None] = None
    response: Union[int, None] = Field(default=None, strict=True, ge=0, le=1)
    error: Union[MessageDeleteError, None] = Field(default=None, repr=False)
