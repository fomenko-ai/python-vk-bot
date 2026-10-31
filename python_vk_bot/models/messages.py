"""The message fields used by this framework, not the entire VK schema."""

from pydantic import Field, JsonValue

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
    geo: Geo | None = None
    payload: str | None = None
    attachments: list[dict[str, JsonValue]] = Field(default_factory=list)


class MessageObject(VKModel):
    message: Message


class MessageEvent(VKModel):
    user_id: int
    peer_id: int
    event_id: str
    conversation_message_id: int | None = None
    # Official schema says string; deployed button events may contain JSON objects.
    # Preserve both without silently decoding or discarding the original value.
    payload: JsonValue = None


class User(VKModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    screen_name: str | None = None


class Keyboard(VKModel):
    buttons: list[list[dict[str, JsonValue]]]
    one_time: bool = False
    inline: bool = False


class MessagePage(VKModel):
    count: int
    items: list[Message]
