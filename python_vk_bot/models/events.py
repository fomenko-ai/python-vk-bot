"""Validate known event objects once and retain unknown event types."""

from __future__ import annotations

from typing import Optional

from pydantic import JsonValue, PrivateAttr, ValidationError, field_validator, model_validator
from typing_extensions import Self

from python_vk_bot.errors import InvalidUpdateError

from .base import VKModel
from .donut import DonutSubscriptionEvent, DonutSubscriptionEventType
from .messages import Message, MessageEvent, MessageObject

_DONUT_EVENT_TYPES = frozenset(event.value for event in DonutSubscriptionEventType)


class Update(VKModel):
    type: str
    group_id: int
    event_id: str
    v: str
    object: JsonValue
    _message: Optional[Message] = PrivateAttr(default=None)
    _message_event: Optional[MessageEvent] = PrivateAttr(default=None)
    _donut_subscription: Optional[DonutSubscriptionEvent] = PrivateAttr(default=None)

    @field_validator("event_id", mode="before")
    @classmethod
    def normalize_event_id(cls, value: object) -> object:
        # Callback documentation also contains a numeric event_id example.
        return str(value) if type(value) is int else value

    @model_validator(mode="after")
    def parse_object(self) -> Self:
        if self.type == "message_new":
            self._message = MessageObject.model_validate(self.object).message
        elif self.type == "message_event":
            self._message_event = MessageEvent.model_validate(self.object)
        elif self.type in _DONUT_EVENT_TYPES:
            self._donut_subscription = DonutSubscriptionEvent.model_validate(self.object)
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, JsonValue]) -> Self:
        # Authentication belongs to the Callback boundary, never to an Update.
        clean = {key: value for key, value in payload.items() if key != "secret"}
        try:
            return cls.model_validate(clean)
        except ValidationError:
            raise InvalidUpdateError("Invalid VK event structure") from None

    @property
    def message(self) -> Optional[Message]:
        return self._message

    @property
    def message_event(self) -> Optional[MessageEvent]:
        return self._message_event

    @property
    def donut_subscription(self) -> Optional[DonutSubscriptionEvent]:
        """Return the parsed subscription event, not a synchronized access status."""
        return self._donut_subscription

    @property
    def user_id(self) -> Optional[int]:
        if self.message is not None:
            return self.message.from_id
        if self.message_event is not None:
            return self.message_event.user_id
        if self.donut_subscription is not None:
            return self.donut_subscription.user_id
        return None

    @property
    def peer_id(self) -> Optional[int]:
        if self.message is not None:
            return self.message.peer_id
        if self.message_event is not None:
            return self.message_event.peer_id
        return None
