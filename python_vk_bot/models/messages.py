"""The message fields used by this framework, not the entire VK schema."""

from __future__ import annotations

from typing import Optional

from pydantic import Field, JsonValue

from .attachments import Attachment, parse_attachment
from .base import VKModel


class Coordinates(VKModel):
    latitude: float
    longitude: float


class Geo(VKModel):
    coordinates: Coordinates


class Message(VKModel):
    id: int
    from_id: int
    peer_id: int
    conversation_message_id: int
    text: str
    geo: Optional[Geo] = None
    payload: Optional[str] = None
    attachments: list[dict[str, JsonValue]] = Field(default_factory=list)

    @property
    def typed_attachments(self) -> list[Attachment]:
        """Return fresh typed views; edits to the raw list remain visible."""
        return [parse_attachment(value) for value in self.attachments]


class MessageObject(VKModel):
    message: Message


class MessageEvent(VKModel):
    user_id: int
    peer_id: int
    event_id: str
    conversation_message_id: Optional[int] = None
    # Official schema says string; deployed button events may contain JSON objects.
    # Preserve both without silently decoding or discarding the original value.
    payload: JsonValue = None


class User(VKModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    screen_name: Optional[str] = None


class Keyboard(VKModel):
    buttons: list[list[dict[str, JsonValue]]]
    one_time: bool = False
    inline: bool = False


class MessagePage(VKModel):
    count: int
    items: list[Message]
