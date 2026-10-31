import asyncio
import json
import logging

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from python_vk_bot import Bot, Keyboard, Message
from python_vk_bot.errors import (
    APIError,
    HTTPError,
    InvalidResponseError,
    LifecycleError,
    NetworkError,
    RateLimitError,
)

from .helpers import MockAPI, form, message


@pytest.mark.parametrize("setting", ["authorization", "access_token", "key", "secret", "closed"])
async def test_rejects_unsafe_or_closed_injected_client(
    client: httpx.AsyncClient, setting: str
) -> None:
    if setting == "authorization":
        client.headers[setting] = "Bearer placeholder"
    elif setting == "closed":
        await client.aclose()
    else:
        client.params = {setting: "placeholder"}
    bot = Bot("placeholder", client=client)
    with pytest.raises((ValueError, LifecycleError)):
        await bot.initialize()
    await bot.shutdown()
    assert client.is_closed is (setting == "closed")


async def test_send_serialization_and_borrowed_client(
    bot: Bot, api: MockAPI, client: httpx.AsyncClient
) -> None:
    api.add({"response": 99})
    keyboard = Keyboard(buttons=[])
    async with bot:
        result = await bot.send_message(
            123,
            "Привет & world",
            random_id=77,
            keyboard=keyboard,
            attachment="photo1_2",
            dont_parse_links=True,
        )
    assert result == 99
    request = api.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.vk.ru/method/messages.send"
    assert request.headers["authorization"] == "Bearer synthetic-community-token"
    data = form(request)
    assert data == {
        "v": "5.199",
        "peer_id": "123",
        "message": "Привет & world",
        "random_id": "77",
        "keyboard": keyboard.model_dump_json(),
        "attachment": "photo1_2",
        "dont_parse_links": "1",
    }
    assert not client.is_closed


async def test_generated_random_id_and_optional_fields(bot: Bot, api: MockAPI) -> None:
    api.add({"response": 5})
    async with bot:
        await bot.send_message(123, attachment="photo1_2")
    data = form(api.requests[0])
    assert 0 < int(data["random_id"]) < 2**31
    assert data["dont_parse_links"] == "0"
    assert "keyboard" not in data


@pytest.mark.parametrize("random_id", [0, 2**31, -(2**31) - 1, True])
async def test_invalid_random_id_never_sends(bot: Bot, api: MockAPI, random_id: int) -> None:
    async with bot:
        with pytest.raises(ValueError, match="random_id"):
            await bot.send_message(1, "text", random_id=random_id)
    assert not api.requests


async def test_send_requires_content(bot: Bot, api: MockAPI) -> None:
    with pytest.raises(ValueError, match="text or an attachment"):
        await bot.send_message(1)
    assert not api.requests


@pytest.mark.parametrize(
    ("identifier", "wire_name"), [("message_id", "message_id"), ("conversation_message_id", "cmid")]
)
async def test_edit_uses_vk_identifier(
    bot: Bot, api: MockAPI, identifier: str, wire_name: str
) -> None:
    api.add({"response": 1})
    async with bot:
        if identifier == "message_id":
            result = await bot.edit_message(123, "edited", message_id=10)
        else:
            result = await bot.edit_message(123, "edited", conversation_message_id=10)
    assert result is True
    data = form(api.requests[0])
    assert data[wire_name] == "10"
    assert "conversation_message_id" not in data


async def test_edit_rejects_ambiguous_identifiers(bot: Bot, api: MockAPI) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        await bot.edit_message(1, "text")
    with pytest.raises(ValueError, match="exactly one"):
        await bot.edit_message(1, "text", message_id=2, conversation_message_id=3)
    assert not api.requests


async def test_forward_uses_source_conversation(bot: Bot, api: MockAPI) -> None:
    api.add({"response": 101})
    async with bot:
        assert (
            await bot.forward_message(999, Message.model_validate(message()), random_id=-10) == 101
        )
    data = form(api.requests[0])
    assert data["peer_id"] == "999"
    assert data["random_id"] == "-10"
    assert json.loads(data["forward"]) == {
        "peer_id": 2_000_000_001,
        "conversation_message_ids": [12],
    }


async def test_typed_fetches_and_event_answer(bot: Bot, api: MockAPI) -> None:
    api.add({"response": [{"id": 7, "first_name": "Name", "extra_field": 123}]})
    api.add({"response": {"count": 1, "items": [message()]}})
    api.add({"response": 1})
    async with bot:
        user = await bot.get_user_info(7)
        found = await bot.get_message(2_000_000_001, 12)
        answered = await bot.send_message_event_answer(
            "button-1", 7, 2_000_000_001, {"type": "show_snackbar", "text": "Done"}
        )
    assert user is not None
    assert user.screen_name is None
    assert user.model_extra == {"extra_field": 123}
    assert found is not None
    assert found.conversation_message_id == 12
    assert form(api.requests[1])["conversation_message_ids"] == "12"
    assert answered is True
    assert json.loads(form(api.requests[2])["event_data"])["type"] == "show_snackbar"


async def test_empty_fetches(bot: Bot, api: MockAPI) -> None:
    api.add({"response": []})
    api.add({"response": {"count": 0, "items": []}})
    async with bot:
        assert await bot.get_user_info(7) is None
        assert await bot.get_message(7, 1) is None


@pytest.mark.parametrize(("code", "error_class"), [(5, APIError), (6, RateLimitError)])
async def test_api_errors_are_safe_and_not_retried(
    bot: Bot, api: MockAPI, code: int, error_class: type[APIError]
) -> None:
    api.add(
        {
            "error": {
                "error_code": code,
                "error_msg": "sensitive body",
                "request_params": [{"key": "access_token", "value": "synthetic-community-token"}],
            }
        }
    )
    async with bot:
        with pytest.raises(error_class) as captured:
            await bot.send_message(1, "private message")
    assert captured.value.code == code
    assert captured.value.method == "messages.send"
    assert "sensitive" not in str(captured.value)
    assert "synthetic-community-token" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_http_errors_are_not_followed_or_retried(bot: Bot, api: MockAPI, status: int) -> None:
    api.add({}, status=status)
    async with bot:
        with pytest.raises(HTTPError) as captured:
            await bot.send_message(1, "hello")
    assert captured.value.status_code == status
    assert len(api.requests) == 1


async def test_network_error_does_not_retry_a_send(bot: Bot, api: MockAPI) -> None:
    api.responses.append(httpx.ReadTimeout("sensitive URL or payload"))
    async with bot:
        with pytest.raises(NetworkError, match="could not complete") as captured:
            await bot.send_message(1, "hello")
    assert "sensitive" not in str(captured.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"response": "not an integer"}, {"error": {"error_code": "invalid"}}]
)
async def test_invalid_responses(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add(payload)
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.send_message(1, "text")


async def test_invalid_json(bot: Bot, api: MockAPI) -> None:
    api.responses.append(httpx.Response(200, content=b"not JSON"))
    async with bot:
        with pytest.raises(InvalidResponseError, match="invalid JSON"):
            await bot.get_user_info(7)


async def test_transport_requires_initialization(bot: Bot) -> None:
    with pytest.raises(LifecycleError, match="Initialize"):
        await bot.get_user_info(7)


async def test_raw_response_and_configuration_protection(bot: Bot, api: MockAPI) -> None:
    api.add({"response": {"unknown": [1, "value", None]}})
    async with bot:
        assert await bot.request("users.get", {"user_ids": 7}) == {"unknown": [1, "value", None]}
        with pytest.raises(ValueError, match="method name"):
            await bot.request("https://example.com/steal", {})
        with pytest.raises(ValueError, match="configuration"):
            await bot.request("users.get", {"access_token": "override"})
    assert len(api.requests) == 1


async def test_poll_does_not_send_token_and_redacts_logs(
    bot: Bot, api: MockAPI, caplog: pytest.LogCaptureFixture
) -> None:
    api.add({"ts": "11", "updates": []})
    with caplog.at_level(logging.INFO, logger="httpx"):
        async with bot:
            await bot.transport.poll(
                "https://poll.example/events", key=SecretStr("synthetic-poll-key"), ts="10", wait=90
            )
    request = api.requests[0]
    assert "authorization" not in request.headers
    assert request.url.params["key"] == "synthetic-poll-key"
    assert request.extensions["timeout"]["read"] > 90
    assert "HTTP Request" in caplog.text
    assert "synthetic-poll-key" not in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "http://poll.example/events",
        "https://user:pass@poll.example/",
        "https://poll.example/?key=value",
    ],
)
async def test_poll_rejects_unexpected_urls(bot: Bot, api: MockAPI, url: str) -> None:
    async with bot:
        with pytest.raises(InvalidResponseError, match="URL"):
            await bot.transport.poll(url, key=SecretStr("placeholder"), ts="1", wait=25)
    assert not api.requests


async def test_request_cancellation_propagates() -> None:
    entered = asyncio.Event()
    released = asyncio.Event()

    async def pending(request: httpx.Request) -> httpx.Response:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            released.set()
        return httpx.Response(200, json={"response": 1})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(pending)) as client,
        Bot("placeholder", client=client) as bot,
        asyncio.timeout(2),
    ):
        task = asyncio.create_task(bot.send_message(1, "text"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert released.is_set()
