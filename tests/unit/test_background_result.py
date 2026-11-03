import asyncio

import httpx
import pytest

from examples import background_result
from python_vk_bot import Application, Bot, Context, Handler, Update

from .helpers import MockAPI, connection, event, form


@pytest.mark.parametrize("text", ["hello", "Привет", ""])
async def test_background_example_dispatches_and_drains_result_without_network(
    application: Application, api: MockAPI, text: str
) -> None:
    skipped: list[str] = []

    async def later(update: Update, context: Context) -> None:
        skipped.append(update.event_id)

    background_result.configure(application)
    application.add_handler(Handler(later), group=1)
    api.add({"response": 10})
    api.add({"response": 11})
    update = Update.from_dict(event(text=f"/background {text}", peer_id=7))
    before = asyncio.all_tasks()
    async with asyncio.timeout(2), application:
        assert await application.process_update(update)
        assert not await application.process_update(update)
        assert len(api.requests) == 1
    assert skipped == []
    assert [request.url.path for request in api.requests] == ["/method/messages.send"] * 2
    assert [form(request)["message"] for request in api.requests] == [
        "Calculation started.",
        f"Result: {len(text)} characters.",
    ]
    assert application.peer_data[7]["last_result"] == f"Result: {len(text)} characters."
    assert asyncio.all_tasks() == before


async def test_background_example_main_with_mocked_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    waiting, cleaned = asyncio.Event(), asyncio.Event()
    polls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == "/method/groups.getLongPollServer":
            return httpx.Response(200, json=connection())
        if request.url.path == "/method/messages.send":
            sent.append(form(request)["message"])
            return httpx.Response(200, json={"response": len(sent)})
        assert request.url.host == "poll.example"
        polls += 1
        if polls == 1:
            return httpx.Response(
                200, json={"ts": "11", "updates": [event(text="/background abc")]}
            )
        waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        raise AssertionError("Idle polling should be cancelled")

    original = background_result.handle_result

    async def handle_and_stop(result: background_result.BackgroundResult, context: Context) -> None:
        await original(result, context)
        await waiting.wait()
        await context.application.stop()

    monkeypatch.setenv("VK_TOKEN", "synthetic-community-token")
    monkeypatch.setenv("VK_GROUP_ID", "42")
    monkeypatch.setattr(background_result, "handle_result", handle_and_stop)
    before = asyncio.all_tasks()
    async with (
        asyncio.timeout(2),
        httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client,
    ):

        def factory(*args: object, **kwargs: object) -> Bot:
            return Bot("placeholder", client=client)

        monkeypatch.setattr(background_result, "Bot", factory)
        await background_result.main()
        assert not client.is_closed
    assert sent == ["Calculation started.", "Result: 3 characters."]
    assert cleaned.is_set()
    assert asyncio.all_tasks() == before
