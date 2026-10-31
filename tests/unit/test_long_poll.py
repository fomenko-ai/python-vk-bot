import asyncio
from contextlib import aclosing

import httpx
import pytest
from pydantic import JsonValue

from python_vk_bot import Bot, LongPoll
from python_vk_bot.errors import APIError, HTTPError, InvalidResponseError, InvalidUpdateError

from .helpers import MockAPI, connection, event


async def test_cursor_and_history_loss(
    bot: Bot, api: MockAPI, caplog: pytest.LogCaptureFixture
) -> None:
    api.add(connection())
    api.add({"ts": "11", "updates": [event()]})
    api.add({"failed": 1, "ts": 20, "extra": "ignored"})
    api.add({"ts": "21", "updates": []})
    async with bot:
        poll = LongPoll(bot, 42)
        updates = await poll.get_updates()
        assert updates[0].event_id == "event-1"
        assert await poll.get_updates() == []
        assert await poll.get_updates() == []
    assert [request.url.params["ts"] for request in api.requests[1:]] == ["10", "11", "20"]
    assert "history was partially lost" in caplog.text


@pytest.mark.parametrize(("failure", "next_ts"), [(2, "10"), (3, "50")])
async def test_refresh_cursor_policy(bot: Bot, api: MockAPI, failure: int, next_ts: str) -> None:
    api.add(connection())
    api.add({"failed": failure})
    api.add(connection("50", "refreshed-key"))
    api.add({"ts": "51", "updates": []})
    async with bot:
        poll = LongPoll(bot, 42)
        assert await poll.get_updates() == []
        assert await poll.get_updates() == []
    assert api.requests[-1].url.params["ts"] == next_ts
    assert api.requests[-1].url.params["key"] == "refreshed-key"


@pytest.mark.parametrize(
    "payload", [None, {"failed": 1}, {"failed": 99}, {"ts": "11"}, {"updates": []}]
)
async def test_invalid_poll_response(bot: Bot, api: MockAPI, payload: JsonValue) -> None:
    api.add(connection())
    api.add(payload)
    async with bot:
        with pytest.raises(InvalidResponseError):
            await LongPoll(bot, 42).get_updates()


@pytest.mark.parametrize("wrong_group", [False, True])
async def test_invalid_batch_does_not_advance_cursor(
    bot: Bot, api: MockAPI, wrong_group: bool
) -> None:
    invalid = event()
    if wrong_group:
        invalid["group_id"] = 99
    else:
        invalid["object"] = {}
    api.add(connection())
    api.add({"ts": "11", "updates": [invalid]})
    api.add({"ts": "12", "updates": []})
    async with bot:
        poll = LongPoll(bot, 42)
        with pytest.raises((InvalidResponseError, InvalidUpdateError)):
            await poll.get_updates()
        await poll.get_updates()
    assert api.requests[-1].url.params["ts"] == "10"


async def test_transient_failures_back_off_and_recover(
    bot: Bot, api: MockAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("python_vk_bot.long_poll.asyncio.sleep", sleep)
    api.add(connection())
    api.responses.append(httpx.ReadTimeout("synthetic timeout"))
    api.add({}, status=503)
    api.add({}, status=429)
    api.add({"ts": "11", "updates": [event()]})
    async with bot, aclosing(LongPoll(bot, 42).listen()) as updates:
        assert (await anext(updates)).event_id == "event-1"
    assert delays == [1.0, 2.0, 4.0]


async def test_rate_limited_session_acquisition_retries(
    bot: Bot, api: MockAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("python_vk_bot.long_poll.asyncio.sleep", sleep)
    api.add({"error": {"error_code": 6, "error_msg": "throttled"}})
    api.add(connection())
    api.add({"ts": "11", "updates": [event()]})
    async with bot, aclosing(LongPoll(bot, 42).listen()) as updates:
        await anext(updates)
    assert delays == [1.0]


async def test_backoff_is_bounded_and_resets_after_empty_success(
    bot: Bot, api: MockAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("python_vk_bot.long_poll.asyncio.sleep", sleep)
    api.add(connection())
    for _ in range(7):
        api.add({}, status=503)
    api.add({"ts": "11", "updates": []})
    api.add({}, status=503)
    api.add({"ts": "12", "updates": [event()]})
    async with bot, aclosing(LongPoll(bot, 42).listen()) as updates:
        await anext(updates)
    assert delays == [1, 2, 4, 8, 16, 30, 30, 0.1, 1]


@pytest.mark.parametrize("http_error", [False, True])
async def test_authentication_errors_are_not_retried(
    bot: Bot, api: MockAPI, http_error: bool
) -> None:
    if http_error:
        api.add({}, status=401)
    else:
        api.add({"error": {"error_code": 5, "error_msg": "unauthorized"}})
    async with bot, aclosing(LongPoll(bot, 42).listen()) as updates:
        with pytest.raises((APIError, HTTPError)):
            await anext(updates)
    assert len(api.requests) == 1


async def test_cancellation_during_backoff(
    bot: Bot, api: MockAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeping = asyncio.Event()

    async def sleep(delay: float) -> None:
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("python_vk_bot.long_poll.asyncio.sleep", sleep)
    api.responses.append(httpx.ConnectError("synthetic failure"))
    async with bot, aclosing(LongPoll(bot, 42).listen()) as updates, asyncio.timeout(2):
        task = asyncio.create_task(anext(updates))
        await sleeping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(api.requests) == 1
