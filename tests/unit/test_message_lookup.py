from typing import cast

import httpx2
import pytest
from pydantic import JsonValue

from python_vk_bot import Bot
from python_vk_bot.errors import APIError, InvalidResponseError, NetworkError, RateLimitError

from .helpers import MockAPI, form, message

PEER = 2_000_000_001


@pytest.mark.parametrize("peer_id", [PEER, -42])
async def test_found_message(bot: Bot, api: MockAPI, peer_id: int) -> None:
    item = message(peer_id=peer_id)
    item["id"] = "100"
    item["extra_field"] = "retained"
    api.add({"response": {"count": 1, "items": [item]}})
    async with bot:
        found = await bot.get_message(peer_id, 12)
    assert found is not None
    assert (found.peer_id, found.conversation_message_id, found.id) == (peer_id, 12, 100)
    assert found.model_extra == {"extra_field": "retained"}
    assert len(api.requests) == 1
    assert api.requests[0].url.path.endswith("/messages.getByConversationMessageId")
    assert form(api.requests[0])["peer_id"] == str(peer_id)
    assert form(api.requests[0])["conversation_message_ids"] == "12"


async def test_confirmed_absence(bot: Bot, api: MockAPI) -> None:
    api.add({"response": {"count": 0, "items": []}})
    async with bot:
        assert await bot.get_message(PEER, 12) is None
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"count": 1, "items": []},
        {"count": 0, "items": [message()]},
        {"count": 2, "items": [message(), message()]},
        {"count": 1, "items": [message(), message()]},
        {"count": -1, "items": []},
        {"count": 0},
        {"items": []},
        {"count": 0, "items": None},
        {"count": 0, "items": {}},
        {"count": 1, "items": [None]},
    ],
)
async def test_invalid_response(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add({"response": payload})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.get_message(PEER, 12)
    assert len(api.requests) == 1


@pytest.mark.parametrize("field", ["count", "peer_id", "conversation_message_id"])
@pytest.mark.parametrize(
    "value", [None, True, False, "1", "12", str(PEER), 1.0, 12.0, float(PEER), 1.5, [], {}]
)
async def test_strict_response_fields(bot: Bot, api: MockAPI, field: str, value: JsonValue) -> None:
    item = message()
    payload: dict[str, JsonValue] = {"count": 1, "items": [item]}
    (payload if field == "count" else item)[field] = value
    api.add({"response": payload})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.get_message(PEER, 12)
    assert len(api.requests) == 1


@pytest.mark.parametrize("field", ["id", "from_id", "peer_id", "conversation_message_id", "text"])
async def test_missing_message_fields(bot: Bot, api: MockAPI, field: str) -> None:
    item = message()
    del item[field]
    api.add({"response": {"count": 1, "items": [item]}})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.get_message(PEER, 12)


@pytest.mark.parametrize("field", ["peer_id", "conversation_message_id"])
async def test_mismatched_identifiers(bot: Bot, api: MockAPI, field: str) -> None:
    item = message(text="private-message-marker")
    item[field] = 99
    api.add({"response": {"count": 1, "items": [item]}})
    async with bot:
        with pytest.raises(InvalidResponseError) as captured:
            await bot.get_message(PEER, 12)
    assert "private-message-marker" not in str(captured.value)
    assert "99" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("field", ["peer_id", "conversation_message_id"])
@pytest.mark.parametrize("value", [None, True, False, 0, "12", 12.0, 1.5, [], {}])
async def test_invalid_inputs_before_http(
    bot: Bot, api: MockAPI, field: str, value: object
) -> None:
    arguments = {"peer_id": PEER, "conversation_message_id": 12}
    arguments[field] = cast(int, value)
    async with bot:
        with pytest.raises(ValueError, match=r"must be|Provide exactly one message identifier"):
            await bot.get_message(**arguments)
    assert not api.requests


async def test_negative_conversation_id_before_http(bot: Bot, api: MockAPI) -> None:
    async with bot:
        with pytest.raises(ValueError, match="positive integers"):
            await bot.get_message(PEER, -1)
    assert not api.requests


@pytest.mark.parametrize("code", [5, 6])
async def test_api_errors(bot: Bot, api: MockAPI, code: int) -> None:
    api.add({"error": {"error_code": code, "error_msg": "private-error-marker"}})
    async with bot:
        with pytest.raises(RateLimitError if code == 6 else APIError) as captured:
            await bot.get_message(PEER, 12)
    assert captured.value.code == code
    assert captured.value.method == "messages.getByConversationMessageId"
    assert "private-error-marker" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("error_type", [httpx2.ReadTimeout, httpx2.ConnectError])
async def test_network_errors(
    bot: Bot, api: MockAPI, error_type: type[httpx2.RequestError]
) -> None:
    api.responses.append(error_type("private-network-marker"))
    async with bot:
        with pytest.raises(NetworkError) as captured:
            await bot.get_message(PEER, 12)
    assert "private-network-marker" not in str(captured.value)
    assert len(api.requests) == 1
