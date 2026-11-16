"""The message fields used by this framework, not the entire VK schema."""

from __future__ import annotations

from typing import Optional, Union

from pydantic import (
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)
from typing_extensions import Self

from python_vk_bot.limits import (
    MAX_BUTTON_LABEL_LENGTH,
    MAX_BUTTONS_PER_ROW,
    MAX_INLINE_BUTTONS,
    MAX_INLINE_ROWS,
    MAX_LOCATION_ROW_BUTTONS,
    MAX_REPLY_BUTTONS,
    MAX_REPLY_ROWS,
    MAX_VKPAY_ROW_BUTTONS,
)

from .attachments import Attachment, parse_attachment
from .base import VKModel
from .keyboards import TypedButton


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
    model_config = ConfigDict(validate_assignment=True)

    buttons: list[list[Union[TypedButton, dict[str, JsonValue]]]]
    one_time: bool = False
    inline: bool = False

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        self._validate_limits()
        return self

    def _validate_limits(self) -> None:
        """Validate dimensions and known labels without exposing button contents."""
        max_rows = MAX_INLINE_ROWS if self.inline else MAX_REPLY_ROWS
        max_buttons = MAX_INLINE_BUTTONS if self.inline else MAX_REPLY_BUTTONS
        self._check_limit("Keyboard rows", len(self.buttons), max_rows)
        self._check_limit("Keyboard buttons", sum(map(len, self.buttons)), max_buttons)
        for row_number, row in enumerate(self.buttons, start=1):
            row_limit = MAX_BUTTONS_PER_ROW
            for button_number, button in enumerate(row, start=1):
                if isinstance(button, dict):
                    action = button.get("action")
                    if not isinstance(action, dict):
                        continue
                    kind = action.get("type")
                    label = action.get("label")
                else:
                    kind = button.type
                    label = getattr(button, "label", None)
                if kind == "location":
                    row_limit = min(row_limit, MAX_LOCATION_ROW_BUTTONS)
                elif kind == "vkpay":
                    row_limit = min(row_limit, MAX_VKPAY_ROW_BUTTONS)
                if kind in ("text", "callback", "open_link") and isinstance(label, str):
                    self._check_limit(
                        f"Row {row_number} button {button_number} label characters",
                        len(label),
                        MAX_BUTTON_LABEL_LENGTH,
                    )
            self._check_limit(f"Row {row_number} buttons", len(row), row_limit)

    @staticmethod
    def _check_limit(subject: str, actual: int, maximum: int) -> None:
        if actual > maximum:
            raise ValueError(f"{subject}: maximum {maximum}, got {actual}")

    @model_serializer(mode="wrap", when_used="json")
    def serialize_keyboard(self, handler: SerializerFunctionWrapHandler) -> dict[str, JsonValue]:
        # Nested lists and raw dictionaries can change without assignment validation.
        self._validate_limits()
        return handler(self)


class MessagePage(VKModel):
    count: int
    items: list[Message]
