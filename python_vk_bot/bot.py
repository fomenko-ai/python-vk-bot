"""Typed wrappers for supported VK community bot methods."""

import json
import re
import secrets
from collections.abc import Mapping
from types import TracebackType
from typing import Literal, Self

import httpx
from pydantic import BaseModel, JsonValue, SecretStr, TypeAdapter, ValidationError

from ._config import DEFAULT_API_VERSION, DEFAULT_TIMEOUT, TransportConfig
from .errors import APIError, InvalidResponseError, RateLimitError
from .models.api import (
    DocumentUpload,
    LongPollServer,
    MessageDeleteResult,
    PhotoUpload,
    UploadServer,
)
from .models.attachments import (
    Attachment,
    AudioMessageAttachment,
    DocumentAttachment,
    Photo,
    PhotoAttachment,
    serialize_attachment,
)
from .models.event_answers import ShowSnackbar
from .models.messages import Keyboard, Message, MessagePage, User
from .transport import FileInput, HTTPTransport, Parameter


def _parse[T: BaseModel](model: type[T], payload: JsonValue) -> T:
    try:
        return model.model_validate(payload)
    except ValidationError:
        raise InvalidResponseError(f"Invalid {model.__name__} response") from None


def _integer(payload: JsonValue) -> int:
    if type(payload) is not int:
        raise InvalidResponseError("Expected an integer VK response")
    return payload


def _random_id(value: int | None) -> int:
    if value is None:
        return secrets.randbelow(2**31 - 1) + 1
    if type(value) is not int or not -(2**31) <= value < 2**31 or value == 0:
        raise ValueError("random_id must be a nonzero signed 32-bit integer")
    return value


def _message_identifier(message_id: int | None, conversation_message_id: int | None) -> int:
    if (message_id is None) == (conversation_message_id is None):
        raise ValueError("Provide exactly one message identifier")
    identifier = message_id if message_id is not None else conversation_message_id
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("Message identifiers must be positive integers")
    return identifier


class Bot:
    def __init__(
        self,
        token: str | SecretStr,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        config = TransportConfig(
            token=token if isinstance(token, SecretStr) else SecretStr(token),
            api_version=api_version,
            timeout=timeout,
        )
        self.transport = HTTPTransport(config, client=client)

    async def initialize(self) -> None:
        await self.transport.initialize()

    async def shutdown(self) -> None:
        await self.transport.shutdown()

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.shutdown()

    async def request(self, method: str, parameters: Mapping[str, Parameter]) -> JsonValue:
        """Access a raw VK result. Nested parameters must be explicitly JSON encoded."""
        return await self.transport.call(method, parameters)

    async def get_long_poll_server(self, group_id: int) -> LongPollServer:
        if group_id <= 0:
            raise ValueError("group_id must be positive")
        result = await self.request("groups.getLongPollServer", {"group_id": group_id})
        return _parse(LongPollServer, result)

    async def get_user_info(self, user_id: int) -> User | None:
        result = await self.request("users.get", {"user_ids": user_id, "fields": "screen_name"})
        try:
            users = TypeAdapter(list[User]).validate_python(result)
        except ValidationError:
            raise InvalidResponseError("Invalid users.get response") from None
        return users[0] if users else None

    async def get_message(self, peer_id: int, conversation_message_id: int) -> Message | None:
        result = await self.request(
            "messages.getByConversationMessageId",
            {"peer_id": peer_id, "conversation_message_ids": conversation_message_id},
        )
        page = _parse(MessagePage, result)
        return page.items[0] if page.items else None

    async def send_message(
        self,
        peer_id: int,
        text: str = "",
        *,
        random_id: int | None = None,
        keyboard: Keyboard | None = None,
        attachment: str | Attachment | None = None,
        dont_parse_links: bool = False,
    ) -> int:
        attachment_id = serialize_attachment(attachment)
        if not text and not attachment_id:
            raise ValueError("Provide text or an attachment")
        result = await self.request(
            "messages.send",
            {
                "peer_id": peer_id,
                "message": text,
                "random_id": _random_id(random_id),
                "keyboard": keyboard.model_dump_json(exclude_none=True) if keyboard else None,
                "attachment": attachment_id,
                "dont_parse_links": dont_parse_links,
            },
        )
        return _integer(result)

    async def edit_message(
        self,
        peer_id: int,
        text: str | None = None,
        *,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
        keyboard: Keyboard | None = None,
        attachment: str | Attachment | None = None,
        dont_parse_links: bool = False,
    ) -> bool:
        """Edit text and/or attachments. None omits a field; an empty string sends it."""
        _message_identifier(message_id, conversation_message_id)
        attachment_id = serialize_attachment(attachment)
        if text is None and attachment_id is None:
            raise ValueError("Provide text or an attachment")
        result = await self.request(
            "messages.edit",
            {
                "peer_id": peer_id,
                "message": text,
                "message_id": message_id,
                "cmid": conversation_message_id,
                "keyboard": keyboard.model_dump_json(exclude_none=True) if keyboard else None,
                "attachment": attachment_id,
                "dont_parse_links": dont_parse_links,
            },
        )
        return _integer(result) == 1

    async def upload_photo(
        self,
        peer_id: int,
        photo: FileInput,
        *,
        filename: str | None = None,
    ) -> PhotoAttachment:
        """Upload and save one photo for messaging; this does not send a message."""
        server = _parse(
            UploadServer, await self.request("photos.getMessagesUploadServer", {"peer_id": peer_id})
        )
        uploaded = _parse(
            PhotoUpload,
            await self.transport.upload(server.upload_url, photo, field="photo", filename=filename),
        )
        result = await self.request(
            "photos.saveMessagesPhoto",
            {"server": uploaded.server, "photo": uploaded.photo, "hash": uploaded.hash},
        )
        if not isinstance(result, list) or len(result) != 1:
            raise InvalidResponseError("Expected one saved photo")
        return PhotoAttachment(photo=_parse(Photo, result[0]))

    async def upload_document(
        self,
        peer_id: int,
        document: FileInput,
        *,
        filename: str | None = None,
        type: Literal["doc", "audio_message"] = "doc",
        title: str | None = None,
        tags: str | None = None,
    ) -> DocumentAttachment | AudioMessageAttachment:
        """Upload and save a document or voice file without sending it."""
        if type not in {"doc", "audio_message"}:
            raise ValueError("Unsupported document upload type")
        server = _parse(
            UploadServer,
            await self.request("docs.getMessagesUploadServer", {"peer_id": peer_id, "type": type}),
        )
        uploaded = _parse(
            DocumentUpload,
            await self.transport.upload(
                server.upload_url, document, field="file", filename=filename
            ),
        )
        result = await self.request(
            "docs.save", {"file": uploaded.file, "title": title, "tags": tags}
        )
        # A save response must contain the requested kind, unlike tolerant inbound views.
        if not isinstance(result, dict) or result.get("type") != type:
            raise InvalidResponseError("Unexpected saved document type")
        if type == "audio_message":
            return _parse(AudioMessageAttachment, result)
        return _parse(DocumentAttachment, result)

    async def edit_message_media(
        self,
        peer_id: int,
        media: FileInput | str | PhotoAttachment,
        *,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
        caption: str | None = None,
        keyboard: Keyboard | None = None,
        filename: str | None = None,
        dont_parse_links: bool = False,
    ) -> bool:
        """Replace a photo, optionally changing text/keyboard; never send a fallback.

        A photo object or VK photo identifier bypasses upload. None omits caption or
        keyboard from messages.edit; supply their desired values explicitly to avoid
        relying on VK's handling of omitted fields. Failed edits leave the saved photo.
        """
        _message_identifier(message_id, conversation_message_id)
        attachment: str | PhotoAttachment
        if isinstance(media, str):
            if re.fullmatch(r"photo-?[1-9][0-9]*_[1-9][0-9]*(?:_[^,\s]+)?", media) is None:
                raise ValueError("media must be a VK photo identifier or a local binary file")
            attachment = media
        elif isinstance(media, PhotoAttachment):
            attachment = media
        else:
            attachment = await self.upload_photo(peer_id, media, filename=filename)
        return await self.edit_message(
            peer_id,
            caption,
            message_id=message_id,
            conversation_message_id=conversation_message_id,
            keyboard=keyboard,
            attachment=attachment,
            dont_parse_links=dont_parse_links,
        )

    async def delete_message(
        self,
        peer_id: int,
        *,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
        delete_for_all: bool = False,
        spam: bool = False,
    ) -> bool:
        """Delete one message. Recipient-side deletion must be explicitly requested."""
        identifier = _message_identifier(message_id, conversation_message_id)
        result = await self.request(
            "messages.delete",
            {
                "peer_id": peer_id,
                "message_ids": message_id,
                "cmids": conversation_message_id,
                "delete_for_all": delete_for_all,
                "spam": spam,
            },
        )
        # VK's method page describes per-ID success; its current schema additionally
        # describes full result objects. Do not mistake an unrecognized response for success.
        if isinstance(result, dict) and message_id is not None:
            status = result.get(str(message_id))
            if type(status) is int and status in (0, 1):
                return status == 1
        if not isinstance(result, list) or len(result) != 1:
            raise InvalidResponseError("Expected one message deletion result")
        deleted = _parse(MessageDeleteResult, result[0])
        actual_id = (
            deleted.message_id if message_id is not None else deleted.conversation_message_id
        )
        if actual_id != identifier or (deleted.peer_id is not None and deleted.peer_id != peer_id):
            raise InvalidResponseError("Message deletion result has an unexpected identifier")
        if deleted.error is not None:
            error_type = RateLimitError if deleted.error.code == 6 else APIError
            raise error_type(deleted.error.code, "messages.delete")
        if deleted.response is None:
            raise InvalidResponseError("Message deletion result has no status")
        return deleted.response == 1

    async def forward_message(
        self, peer_id: int, message: Message, *, random_id: int | None = None
    ) -> int:
        # The source is the conversation, which need not be the author's user ID.
        forward = {
            "peer_id": message.peer_id,
            "conversation_message_ids": [message.conversation_message_id],
        }
        result = await self.request(
            "messages.send",
            {
                "peer_id": peer_id,
                "random_id": _random_id(random_id),
                "forward": json.dumps(forward),
            },
        )
        return _integer(result)

    async def send_message_event_answer(
        self,
        event_id: str,
        user_id: int,
        peer_id: int,
        event_data: ShowSnackbar | Mapping[str, JsonValue] | None = None,
    ) -> bool:
        if isinstance(event_data, ShowSnackbar):
            serialized_event_data = event_data.model_dump_json(by_alias=True)
        else:
            serialized_event_data = json.dumps(dict(event_data)) if event_data is not None else None
        result = await self.request(
            "messages.sendMessageEventAnswer",
            {
                "event_id": event_id,
                "user_id": user_id,
                "peer_id": peer_id,
                "event_data": serialized_event_data,
            },
        )
        return _integer(result) == 1
