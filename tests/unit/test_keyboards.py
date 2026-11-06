"""Typed button validation and VK serialization, without live requests."""

from __future__ import annotations

import json
from typing import Literal, Optional, Union

import pytest
from pydantic import BaseModel, Field, JsonValue, ValidationError
from pydantic_core import PydanticSerializationError

from python_vk_bot import (
    Bot,
    ButtonColor,
    ButtonType,
    CallbackButton,
    Keyboard,
    LocationButton,
    OpenLinkButton,
    TextButton,
)

from .helpers import MockAPI, form


class ActionPayload(BaseModel):
    action: Literal["confirm", "cancel"] = Field(serialization_alias="cmd")


@pytest.mark.parametrize(
    ("button_class", "kind"),
    [(TextButton, ButtonType.TEXT), (CallbackButton, ButtonType.CALLBACK)],
)
@pytest.mark.parametrize(
    ("payload", "wire_payload"),
    [
        pytest.param({"cmd": "confirm"}, '{"cmd":"confirm"}', id="dictionary"),
        pytest.param(ActionPayload(action="confirm"), '{"cmd":"confirm"}', id="model-alias"),
        pytest.param('{ "cmd": "confirm" }', '{ "cmd": "confirm" }', id="encoded-string"),
        pytest.param(None, None, id="omitted"),
    ],
)
def test_button_serializes_vk_action_and_payload(
    button_class: Union[type[TextButton], type[CallbackButton]],
    kind: ButtonType,
    payload: Union[dict[str, JsonValue], BaseModel, str, None],
    wire_payload: Optional[str],
) -> None:
    button = button_class(label="Choose", payload=payload, color=ButtonColor.POSITIVE)
    action: dict[str, JsonValue] = {"type": kind.value, "label": "Choose"}
    if wire_payload is not None:
        action["payload"] = wire_payload
    expected = {"action": action, "color": "positive"}

    assert button.type is kind
    assert str(button.type) == kind.value
    assert json.loads(button.model_dump_json()) == expected
    assert button.model_dump(mode="json") == expected


def test_model_payload_retains_subclass_fields_and_python_dump_shape() -> None:
    class OrderPayload(ActionPayload):
        order_id: int

    payload = OrderPayload(action="confirm", order_id=42)
    button = CallbackButton(label="Choose", payload=payload)

    assert button.payload is payload
    assert button.model_dump() == {
        "type": ButtonType.CALLBACK,
        "label": "Choose",
        "payload": {"action": "confirm", "order_id": 42},
        "color": ButtonColor.SECONDARY,
    }
    wire = json.loads(button.model_dump_json())
    assert json.loads(wire["action"]["payload"]) == {"cmd": "confirm", "order_id": 42}


@pytest.mark.parametrize("color", list(ButtonColor))
def test_color_strings_validate_to_enum_and_serialize_to_vk_values(color: ButtonColor) -> None:
    button = TextButton.model_validate({"label": "Choose", "color": color.value})

    assert button.color is color
    assert str(button.color) == color.value
    assert json.loads(button.model_dump_json())["color"] == color.value


@pytest.mark.parametrize(
    ("button_class", "wrong_type"),
    [(TextButton, "callback"), (CallbackButton, "text")],
)
def test_action_type_cannot_be_changed_at_construction_or_assignment(
    button_class: Union[type[TextButton], type[CallbackButton]], wrong_type: str
) -> None:
    with pytest.raises(ValidationError, match="type"):
        button_class.model_validate({"label": "Choose", "type": wrong_type})

    button = button_class(label="Choose")
    original_type = button.type
    with pytest.raises(ValidationError, match="type"):
        button.type = wrong_type  # ty: ignore[invalid-assignment] -- invalid input boundary
    assert button.type is original_type


@pytest.mark.parametrize(
    "invalid_fields",
    [
        pytest.param({"color": "unknown"}, id="invalid-color"),
        pytest.param({"unexpected": True}, id="extra-field"),
        pytest.param({"label": None}, id="invalid-label"),
    ],
)
def test_invalid_typed_button_fields_are_rejected(invalid_fields: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        CallbackButton.model_validate({"label": "Choose", **invalid_fields})


def test_color_assignment_is_validated() -> None:
    button = TextButton(label="Choose")
    button.color = ButtonColor.NEGATIVE
    assert button.color is ButtonColor.NEGATIVE

    with pytest.raises(ValidationError, match="color"):
        button.color = "unknown"  # ty: ignore[invalid-assignment] -- invalid input boundary
    assert button.color is ButtonColor.NEGATIVE


def test_non_finite_dictionary_payload_is_not_sent_as_json() -> None:
    button = CallbackButton(label="Choose", payload={"value": float("nan")})

    with pytest.raises(PydanticSerializationError, match="JSON"):
        button.model_dump_json()


def test_mixed_keyboard_preserves_raw_actions_and_serializes_typed_instances() -> None:
    raw: dict[str, JsonValue] = {
        "action": {"type": "future_action", "extra": {"enabled": True}},
        "future_field": [1, 2],
    }
    keyboard = Keyboard(
        inline=True,
        buttons=[
            [TextButton(label="Help"), raw],
            [CallbackButton(label="Next"), OpenLinkButton(label="Guide", link="https://vk.com")],
            [LocationButton()],
        ],
        future_keyboard_field=True,
    )
    wire = json.loads(keyboard.model_dump_json(exclude_none=True))

    assert wire == {
        "inline": True,
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "Help"}, "color": "secondary"}, raw],
            [
                {"action": {"type": "callback", "label": "Next"}, "color": "secondary"},
                {"action": {"type": "open_link", "label": "Guide", "link": "https://vk.com"}},
            ],
            [{"action": {"type": "location"}}],
        ],
        "future_keyboard_field": True,
    }
    assert Keyboard.model_validate(wire).model_dump(mode="json") == wire
    assert raw == {
        "action": {"type": "future_action", "extra": {"enabled": True}},
        "future_field": [1, 2],
    }


@pytest.mark.parametrize("operation", ["send", "edit"])
async def test_typed_keyboard_reaches_vk_as_nested_json(
    bot: Bot, api: MockAPI, operation: str
) -> None:
    api.add({"response": 1})
    keyboard = Keyboard(
        inline=True,
        buttons=[
            [
                CallbackButton(
                    label="Confirm",
                    payload=ActionPayload(action="confirm"),
                    color=ButtonColor.POSITIVE,
                ),
                CallbackButton(
                    label="Cancel", payload={"cmd": "cancel"}, color=ButtonColor.NEGATIVE
                ),
            ],
            [OpenLinkButton(label="Guide", link="https://vk.com", payload={"page": "guide"})],
            [LocationButton()],
        ],
    )

    async with bot:
        if operation == "send":
            await bot.send_message(7, "Choose", keyboard=keyboard, random_id=17)
        else:
            await bot.edit_message(7, "Choose", conversation_message_id=12, keyboard=keyboard)

    assert len(api.requests) == 1
    assert api.requests[0].url.path == f"/method/messages.{operation}"
    assert json.loads(form(api.requests[0])["keyboard"]) == {
        "inline": True,
        "one_time": False,
        "buttons": [
            [
                {
                    "action": {
                        "type": "callback",
                        "label": "Confirm",
                        "payload": '{"cmd":"confirm"}',
                    },
                    "color": "positive",
                },
                {
                    "action": {
                        "type": "callback",
                        "label": "Cancel",
                        "payload": '{"cmd":"cancel"}',
                    },
                    "color": "negative",
                },
            ],
            [
                {
                    "action": {
                        "type": "open_link",
                        "label": "Guide",
                        "link": "https://vk.com",
                        "payload": '{"page":"guide"}',
                    }
                }
            ],
            [{"action": {"type": "location"}}],
        ],
    }


@pytest.mark.parametrize(
    ("button_class", "fields", "kind"),
    [
        (OpenLinkButton, {"label": "Guide", "link": "https://vk.com"}, ButtonType.OPEN_LINK),
        (LocationButton, {}, ButtonType.LOCATION),
    ],
)
@pytest.mark.parametrize(
    ("payload", "wire_payload"),
    [
        pytest.param({"cmd": "confirm"}, '{"cmd":"confirm"}', id="dictionary"),
        pytest.param(ActionPayload(action="confirm"), '{"cmd":"confirm"}', id="model-alias"),
        pytest.param('{ "cmd": "confirm" }', '{ "cmd": "confirm" }', id="encoded-string"),
        pytest.param(None, None, id="omitted"),
    ],
)
def test_uncolored_button_payload_and_vk_shape(
    button_class: type[OpenLinkButton] | type[LocationButton],
    fields: dict[str, str],
    kind: ButtonType,
    payload: dict[str, JsonValue] | BaseModel | str | None,
    wire_payload: str | None,
) -> None:
    button = button_class.model_validate({**fields, "payload": payload})
    action: dict[str, JsonValue] = {"type": kind.value, **fields}
    if wire_payload is not None:
        action["payload"] = wire_payload

    assert button.type is kind
    assert button.model_dump(mode="json") == {"action": action}
    assert json.loads(button.model_dump_json(exclude_none=True)) == {"action": action}
    assert button.model_dump()["payload"] == (
        payload.model_dump() if isinstance(payload, BaseModel) else payload
    )


@pytest.mark.parametrize(
    ("button_class", "fields"),
    [
        (OpenLinkButton, {"label": "Guide", "link": "https://vk.com", "color": "primary"}),
        (OpenLinkButton, {"label": "Guide"}),
        (OpenLinkButton, {"link": "https://vk.com"}),
        (LocationButton, {"label": "Send location"}),
        (LocationButton, {"color": "primary"}),
        (LocationButton, {"unexpected": True}),
    ],
)
def test_new_buttons_reject_unsupported_or_missing_fields(
    button_class: type[OpenLinkButton] | type[LocationButton], fields: dict[str, JsonValue]
) -> None:
    with pytest.raises(ValidationError):
        button_class.model_validate(fields)


@pytest.mark.parametrize(
    "button",
    [OpenLinkButton(label="Guide", link="https://vk.com"), LocationButton()],
)
def test_new_button_type_is_fixed(button: OpenLinkButton | LocationButton) -> None:
    original_type = button.type
    with pytest.raises(ValidationError, match="type"):
        type(button).model_validate({**button.model_dump(), "type": "text"})
    with pytest.raises(ValidationError, match="type"):
        button.type = "text"  # ty: ignore[invalid-assignment] -- invalid input boundary
    assert button.type is original_type
