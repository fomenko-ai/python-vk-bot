"""Convenient outgoing button models with VK JSON serialization."""

import json
from enum import StrEnum
from typing import Annotated, Literal

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


class ButtonColor(StrEnum):
    """Colors documented by the VK keyboard guide."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ButtonType(StrEnum):
    """Action types supported by the typed button models."""

    TEXT = "text"
    CALLBACK = "callback"


class _LabeledButton(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, hide_input_in_errors=True, allow_inf_nan=False
    )

    label: str = Field(repr=False)
    payload: dict[str, JsonValue] | SerializeAsAny[BaseModel] | str | None = Field(
        default=None, repr=False
    )
    color: ButtonColor = ButtonColor.SECONDARY

    @field_serializer("payload", when_used="json")
    def serialize_payload(self, value: dict[str, JsonValue] | BaseModel | str | None) -> str | None:
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


class TextButton(_LabeledButton):
    """Send the label and optional payload as a message, handled by MessageHandler."""

    type: Literal[ButtonType.TEXT] = ButtonType.TEXT


class CallbackButton(_LabeledButton):
    """Emit a message_event, handled by MessageEventHandler."""

    type: Literal[ButtonType.CALLBACK] = ButtonType.CALLBACK


type TypedButton = Annotated[TextButton | CallbackButton, Field(discriminator="type")]
