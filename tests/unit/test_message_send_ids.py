"""Detailed sends use HTTP mocks and never contact VK."""

import json
from typing import cast

import httpx
import pytest
from pydantic import JsonValue, ValidationError

from python_vk_bot import Bot, Keyboard, Message, MessageSendResult
from python_vk_bot.errors import APIError, InvalidResponseError, NetworkError, RateLimitError
from python_vk_bot.models import MessageSendResult as ExportedMessageSendResult
from python_vk_bot.models.attachments import Photo, PhotoAttachment

from .helpers import MockAPI, form, message

PEER_ID = 2_000_000_002
SOURCE_PEER_ID = 2_000_000_001


def sent_item(**overrides: JsonValue) -> dict[str, JsonValue]:
    return {
        "peer_id": PEER_ID,
        "message_id": 0,
        "conversation_message_id": 37,
        **overrides,
    }


async def send(bot: Bot, *, forwarding: bool, random_id: int | None = None) -> MessageSendResult:
    if forwarding:
        return await bot.forward_message_and_get_ids(
            PEER_ID,
            from_peer_id=SOURCE_PEER_ID,
            conversation_message_id=12,
            random_id=random_id,
        )
    return await bot.send_message_and_get_ids(PEER_ID, "Hello", random_id=random_id)


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize("message_id", [0, 105])
async def test_detailed_send_ids_and_generated_random_id(
    bot: Bot, api: MockAPI, forwarding: bool, message_id: int, client: httpx.AsyncClient
) -> None:
    api.add({"response": [sent_item(message_id=message_id, future={"value": 1})]})
    async with bot:
        result = await send(bot, forwarding=forwarding)
    assert isinstance(result, MessageSendResult)
    assert ExportedMessageSendResult is MessageSendResult
    assert result.peer_id == PEER_ID
    assert result.message_id == (message_id or None)
    assert result.conversation_message_id == 37
    assert result.model_extra == {"future": {"value": 1}}
    request = api.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.vk.ru/method/messages.send"
    data = form(request)
    assert data["peer_ids"] == str(PEER_ID)
    assert "peer_id" not in data
    assert 0 < int(data["random_id"]) < 2**31
    if forwarding:
        assert set(data) == {"peer_ids", "random_id", "forward", "v"}
        assert json.loads(data["forward"]) == {
            "peer_id": SOURCE_PEER_ID,
            "conversation_message_ids": [12],
        }
    assert len(api.requests) == 1
    assert not client.is_closed


async def test_detailed_send_parameters(bot: Bot, api: MockAPI) -> None:
    api.add({"response": [sent_item()]})
    keyboard = Keyboard(buttons=[])
    attachment = PhotoAttachment(photo=Photo(id=2, owner_id=-42))
    async with bot:
        await bot.send_message_and_get_ids(
            PEER_ID,
            "Привет & world",
            random_id=-77,
            keyboard=keyboard,
            attachment=attachment,
            dont_parse_links=True,
        )
    assert form(api.requests[0]) == {
        "v": "5.199",
        "peer_ids": str(PEER_ID),
        "message": "Привет & world",
        "random_id": "-77",
        "keyboard": keyboard.model_dump_json(),
        "attachment": "photo-42_2",
        "dont_parse_links": "1",
    }


async def test_attachment_only_send_to_community_peer(bot: Bot, api: MockAPI) -> None:
    api.add({"response": [sent_item(peer_id=-42)]})
    async with bot:
        result = await bot.send_message_and_get_ids(-42, attachment="photo-42_2")
    assert result.peer_id == -42
    data = form(api.requests[0])
    assert data["peer_ids"] == "-42"
    assert data["attachment"] == "photo-42_2"
    assert data["dont_parse_links"] == "0"
    assert "keyboard" not in data


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize("random_id", [-(2**31), -1, 1, 2**31 - 1])
async def test_explicit_random_id_preserved(
    bot: Bot, api: MockAPI, forwarding: bool, random_id: int
) -> None:
    api.add({"response": [sent_item()]})
    async with bot:
        await send(bot, forwarding=forwarding, random_id=random_id)
    assert form(api.requests[0])["random_id"] == str(random_id)


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize("random_id", [0, 2**31, -(2**31) - 1, True, 1.5, "1"])
async def test_invalid_random_id_never_sends(
    bot: Bot, api: MockAPI, forwarding: bool, random_id: object
) -> None:
    async with bot:
        with pytest.raises(ValueError, match="random_id"):
            await send(bot, forwarding=forwarding, random_id=cast(int, random_id))
    assert not api.requests


async def test_empty_send_never_sends(bot: Bot, api: MockAPI) -> None:
    with pytest.raises(ValueError, match="text or an attachment"):
        await bot.send_message_and_get_ids(PEER_ID)
    assert not api.requests


@pytest.mark.parametrize("field", ["peer_id", "from_peer_id", "conversation_message_id"])
@pytest.mark.parametrize("value", [0, True, "1", 1.5])
async def test_forward_invalid_identifiers_never_send(
    bot: Bot, api: MockAPI, field: str, value: object
) -> None:
    identifiers = {
        "peer_id": PEER_ID,
        "from_peer_id": SOURCE_PEER_ID,
        "conversation_message_id": 12,
    }
    identifiers[field] = cast(int, value)
    with pytest.raises(ValueError, match=r"Message identifiers|peer_id"):
        await bot.forward_message_and_get_ids(**identifiers)
    assert not api.requests


async def test_forward_rejects_negative_source_message_id(bot: Bot, api: MockAPI) -> None:
    with pytest.raises(ValueError, match="positive"):
        await bot.forward_message_and_get_ids(
            PEER_ID, from_peer_id=SOURCE_PEER_ID, conversation_message_id=-12
        )
    assert not api.requests


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize(("code", "error_class"), [(901, APIError), (6, RateLimitError)])
@pytest.mark.parametrize("omit_ids", [False, True])
async def test_recipient_errors_are_safe_and_not_retried(
    bot: Bot,
    api: MockAPI,
    forwarding: bool,
    code: int,
    error_class: type[APIError],
    omit_ids: bool,
) -> None:
    item = sent_item(conversation_message_id=0)
    if omit_ids:
        del item["message_id"]
        del item["conversation_message_id"]
    item["error"] = {"code": code, "description": "private message or token"}
    api.add({"response": [item]})
    async with bot:
        with pytest.raises(error_class) as captured:
            await send(bot, forwarding=forwarding)
    assert captured.value.code == code
    assert captured.value.method == "messages.send"
    assert "private" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize("response", [None, 0, {}, [], [None], [sent_item(), sent_item()]])
async def test_invalid_response_shape(
    bot: Bot, api: MockAPI, forwarding: bool, response: JsonValue
) -> None:
    api.add({"response": response})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await send(bot, forwarding=forwarding)
    assert len(api.requests) == 1


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("peer_id", PEER_ID + 1),
        ("peer_id", str(PEER_ID)),
        ("peer_id", True),
        ("message_id", None),
        ("message_id", -1),
        ("message_id", "1"),
        ("message_id", True),
        ("conversation_message_id", None),
        ("conversation_message_id", 0),
        ("conversation_message_id", -1),
        ("conversation_message_id", "37"),
        ("conversation_message_id", True),
        ("error", {}),
        ("error", {"code": "6"}),
        ("error", {"code": True}),
        ("error", {"code": 0}),
        ("error", "private payload"),
    ],
)
async def test_invalid_recipient_result(
    bot: Bot, api: MockAPI, forwarding: bool, field: str, value: JsonValue
) -> None:
    api.add({"response": [sent_item(**{field: value})]})
    async with bot:
        with pytest.raises(InvalidResponseError) as captured:
            await send(bot, forwarding=forwarding)
    assert "private" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("field", ["peer_id", "message_id", "conversation_message_id"])
async def test_missing_success_ids(bot: Bot, api: MockAPI, field: str) -> None:
    item = sent_item()
    del item[field]
    api.add({"response": [item]})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await send(bot, forwarding=False)


@pytest.mark.parametrize("forwarding", [False, True])
async def test_outer_api_error(bot: Bot, api: MockAPI, forwarding: bool) -> None:
    api.add({"error": {"error_code": 6, "error_msg": "private error"}})
    async with bot:
        with pytest.raises(RateLimitError) as captured:
            await send(bot, forwarding=forwarding)
    assert captured.value.code == 6
    assert captured.value.method == "messages.send"
    assert "private" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("forwarding", [False, True])
async def test_network_failure_does_not_resend(bot: Bot, api: MockAPI, forwarding: bool) -> None:
    api.responses.append(httpx.ReadTimeout("private payload"))
    async with bot:
        with pytest.raises(NetworkError):
            await send(bot, forwarding=forwarding)
    assert len(api.requests) == 1


async def test_send_then_edit_by_conversation_id(bot: Bot, api: MockAPI) -> None:
    api.add({"response": [sent_item()]})
    api.add({"response": 1})
    async with bot:
        result = await send(bot, forwarding=False)
        assert await bot.edit_message(
            result.peer_id, "Edited", conversation_message_id=result.conversation_message_id
        )
    data = form(api.requests[1])
    assert data["peer_id"] == str(PEER_ID)
    assert data["cmid"] == "37"
    assert "message_id" not in data


@pytest.mark.parametrize("forwarding", [False, True])
@pytest.mark.parametrize("message_id", [0, 105])
async def test_integer_send_contract_preserved(
    bot: Bot, api: MockAPI, forwarding: bool, message_id: int
) -> None:
    api.add({"response": message_id})
    async with bot:
        if forwarding:
            result = await bot.forward_message(
                PEER_ID, Message.model_validate(message()), random_id=-77
            )
        else:
            result = await bot.send_message(PEER_ID, "Hello", random_id=-77)
    assert type(result) is int
    assert result == message_id
    data = form(api.requests[0])
    assert data["peer_id"] == str(PEER_ID)
    assert "peer_ids" not in data
    assert data["random_id"] == "-77"


@pytest.mark.parametrize(
    ("field", "value"),
    [("peer_id", 0), ("peer_id", True), ("message_id", 0), ("conversation_message_id", 0)],
)
def test_public_model_rejects_unusable_ids(field: str, value: JsonValue) -> None:
    item = sent_item(message_id=105)
    item[field] = value
    with pytest.raises(ValidationError):
        MessageSendResult.model_validate(item)
