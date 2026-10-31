"""Typed wrappers for supported VK community bot methods."""

import json
import secrets
from collections.abc import Mapping
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, JsonValue, SecretStr, TypeAdapter, ValidationError

from ._config import DEFAULT_API_VERSION, DEFAULT_TIMEOUT, TransportConfig
from .errors import InvalidResponseError
from .models.api import LongPollServer
from .models.messages import Keyboard, Message, MessagePage, User
from .transport import HTTPTransport, Parameter


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
        attachment: str | None = None,
        dont_parse_links: bool = False,
    ) -> int:
        if not text and not attachment:
            raise ValueError("Provide text or an attachment")
        result = await self.request(
            "messages.send",
            {
                "peer_id": peer_id,
                "message": text,
                "random_id": _random_id(random_id),
                "keyboard": keyboard.model_dump_json(exclude_none=True) if keyboard else None,
                "attachment": attachment,
                "dont_parse_links": dont_parse_links,
            },
        )
        return _integer(result)

    async def edit_message(
        self,
        peer_id: int,
        text: str,
        *,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
        keyboard: Keyboard | None = None,
        dont_parse_links: bool = False,
    ) -> bool:
        if (message_id is None) == (conversation_message_id is None):
            raise ValueError("Provide exactly one message identifier")
        result = await self.request(
            "messages.edit",
            {
                "peer_id": peer_id,
                "message": text,
                "message_id": message_id,
                "cmid": conversation_message_id,
                "keyboard": keyboard.model_dump_json(exclude_none=True) if keyboard else None,
                "dont_parse_links": dont_parse_links,
            },
        )
        return _integer(result) == 1

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
        event_data: Mapping[str, JsonValue] | None = None,
    ) -> bool:
        result = await self.request(
            "messages.sendMessageEventAnswer",
            {
                "event_id": event_id,
                "user_id": user_id,
                "peer_id": peer_id,
                "event_data": json.dumps(dict(event_data)) if event_data is not None else None,
            },
        )
        return _integer(result) == 1
