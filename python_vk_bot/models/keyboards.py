"""Convenient outgoing button models with VK JSON serialization."""

from __future__ import annotations

import json
import sys
from typing import Annotated, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializeAsAny,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
)
from typing_extensions import TypeAlias

if sys.version_info >= (3, 11):
    from enum import StrEnum as _StrEnum
else:
    from enum import Enum

    class _StrEnum(str, Enum):
        """String-valued enums with value-based str() on Python 3.9/3.10."""

        def __str__(self) -> str:
            return str(self.value)


class ButtonColor(_StrEnum):
    """Colors documented by the VK keyboard guide."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ButtonType(_StrEnum):
    """Action types supported by the typed button models."""

    TEXT = "text"
    CALLBACK = "callback"
    OPEN_LINK = "open_link"
    LOCATION = "location"


class _Button(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, hide_input_in_errors=True, allow_inf_nan=False
    )

    payload: Union[dict[str, JsonValue], SerializeAsAny[BaseModel], str, None] = Field(
        default=None, repr=False
    )

    @field_serializer("payload", when_used="json")
    def serialize_payload(
        self, value: Union[dict[str, JsonValue], BaseModel, str, None]
    ) -> Optional[str]:
        if isinstance(value, BaseModel):
            return value.model_dump_json(by_alias=True)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return value

    @model_serializer(mode="wrap", when_used="json")
    def serialize_button(self, handler: SerializerFunctionWrapHandler) -> dict[str, JsonValue]:
        action: dict[str, JsonValue] = handler(self)
        button: dict[str, JsonValue] = {"action": action}
        if "color" in action:
            button["color"] = action.pop("color")
        # Absence of payload is represented by an omitted action field, never JSON null.
        if action.get("payload") is None:
            action.pop("payload", None)
        return button


class _LabeledButton(_Button):
    label: str = Field(repr=False)
    color: ButtonColor = ButtonColor.SECONDARY


class TextButton(_LabeledButton):
    """Send the label and optional payload as a message, handled by MessageHandler."""

    type: Literal[ButtonType.TEXT] = ButtonType.TEXT


class CallbackButton(_LabeledButton):
    """Emit a message_event, handled by MessageEventHandler."""

    type: Literal[ButtonType.CALLBACK] = ButtonType.CALLBACK


class OpenLinkButton(_Button):
    """Open a URL using VK's link action, without a configurable color."""

    type: Literal[ButtonType.OPEN_LINK] = ButtonType.OPEN_LINK
    label: str = Field(repr=False)
    link: str = Field(repr=False)


class LocationButton(_Button):
    """Let the user choose a location and send it as a message with geo data."""

    type: Literal[ButtonType.LOCATION] = ButtonType.LOCATION


TypedButton: TypeAlias = Annotated[
    Union[TextButton, CallbackButton, OpenLinkButton, LocationButton], Field(discriminator="type")
]
