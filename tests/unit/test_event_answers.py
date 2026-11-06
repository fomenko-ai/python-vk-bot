"""Native event-answer models and compatibility at the mocked API boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType

import pytest
from pydantic import JsonValue, ValidationError

from python_vk_bot import Bot, LocationButton, OpenLinkButton, ShowSnackbar, models

from .helpers import MockAPI, form


def test_new_models_are_exported_from_both_public_namespaces() -> None:
    assert models.OpenLinkButton is OpenLinkButton
    assert models.LocationButton is LocationButton
    assert models.ShowSnackbar is ShowSnackbar


def test_snackbar_text_limit_and_safe_representation() -> None:
    text = "я" * 90
    answer = ShowSnackbar(text=text)
    assert answer.model_dump() == {"type": "show_snackbar", "text": text}
    assert json.loads(answer.model_dump_json()) == {"type": "show_snackbar", "text": text}
    assert text not in repr(answer)

    with pytest.raises(ValidationError, match="90") as captured:
        ShowSnackbar(text=text + "я")
    assert text not in str(captured.value)


def test_snackbar_assignment_preserves_valid_text_and_type() -> None:
    answer = ShowSnackbar(text="Done")
    with pytest.raises(ValidationError, match="90"):
        answer.text = "x" * 91
    assert answer.text == "Done"
    with pytest.raises(ValidationError, match="type"):
        answer.type = "open_link"  # ty: ignore[invalid-assignment] -- invalid input boundary
    assert answer.type == "show_snackbar"


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "open_link", "text": "Done"},
        {"text": "Done", "extra": True},
        {},
        {"text": None},
    ],
)
def test_snackbar_rejects_invalid_fields(fields: dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        ShowSnackbar.model_validate(fields)


@pytest.mark.parametrize("positional", [False, True])
@pytest.mark.parametrize(
    ("event_data", "expected"),
    [
        (ShowSnackbar(text="Готово"), {"type": "show_snackbar", "text": "Готово"}),
        ({"type": "show_snackbar", "text": "x" * 91}, {"type": "show_snackbar", "text": "x" * 91}),
        (
            MappingProxyType({"type": "open_link", "link": "https://vk.com"}),
            {"type": "open_link", "link": "https://vk.com"},
        ),
        ({}, {}),
        (None, None),
    ],
)
async def test_event_answer_serializes_once_and_preserves_existing_calls(
    bot: Bot,
    api: MockAPI,
    event_data: ShowSnackbar | Mapping[str, JsonValue] | None,
    expected: dict[str, JsonValue] | None,
    positional: bool,
) -> None:
    api.add({"response": 1})
    async with bot:
        if positional:
            result = await bot.send_message_event_answer("click-1", 7, 123, event_data)
        else:
            result = await bot.send_message_event_answer(
                event_id="click-1", user_id=7, peer_id=123, event_data=event_data
            )

    assert result is True
    assert len(api.requests) == 1
    assert api.requests[0].url.path == "/method/messages.sendMessageEventAnswer"
    parameters = form(api.requests[0])
    assert parameters["event_id"] == "click-1"
    assert parameters["user_id"] == "7"
    assert parameters["peer_id"] == "123"
    if expected is None:
        assert "event_data" not in parameters
    else:
        assert json.loads(parameters["event_data"]) == expected


async def test_event_answer_can_omit_optional_data(bot: Bot, api: MockAPI) -> None:
    api.add({"response": 0})
    async with bot:
        assert await bot.send_message_event_answer("click-1", 7, 123) is False
    assert "event_data" not in form(api.requests[0])
