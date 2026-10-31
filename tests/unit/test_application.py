import asyncio

import httpx
import pytest

from python_vk_bot import (
    Application,
    Bot,
    CommandHandler,
    Context,
    Handler,
    MessageEventHandler,
    MessageHandler,
    Update,
)
from python_vk_bot.errors import APIError, LifecycleError

from .helpers import MockAPI, connection, event


async def test_ordered_groups_first_match_and_scoped_state(application: Application) -> None:
    calls: list[str] = []
    contexts: list[Context] = []

    async def first(update: Update, context: Context) -> None:
        calls.append("first")
        contexts.append(context)
        context.user_data["seen"] = update.event_id

    async def skipped(update: Update, context: Context) -> None:
        calls.append("skipped")

    async def last(update: Update, context: Context) -> None:
        calls.append("last")

    application.add_handler(Handler(last), group=10)
    application.add_handler(MessageHandler(first), group=-1)
    application.add_handler(Handler(skipped), group=-1)
    async with application:
        await application.process_update(Update.from_dict(event()))
        await application.process_update(Update.from_dict(event("event-2", peer_id=99)))
        await application.process_update(Update.from_dict(event("event-3", user_id=8)))
    assert calls == ["first", "last"] * 3
    assert contexts[0].user_data is contexts[1].user_data
    assert contexts[0].user_data is not contexts[2].user_data
    assert contexts[0].peer_data is contexts[2].peer_data
    assert contexts[0].peer_data is not contexts[1].peer_data
    assert contexts[0].bot_data is application.bot_data


@pytest.mark.parametrize(
    ("text", "matches"),
    [
        ("/start", True),
        (" /start value", True),
        ("/starter", False),
        ("/start@otherbot", False),
        ("", False),
    ],
)
def test_command_matching(text: str, matches: bool) -> None:
    async def callback(update: Update, context: Context) -> None:
        pass

    assert (
        CommandHandler("start", callback).check_update(Update.from_dict(event(text=text)))
        is matches
    )


def test_event_handler_does_not_match_messages() -> None:
    async def callback(update: Update, context: Context) -> None:
        pass

    handler = MessageEventHandler(callback)
    assert not handler.check_update(Update.from_dict(event()))
    assert handler.check_update(
        Update.from_dict(
            {
                "type": "message_event",
                "group_id": 42,
                "event_id": "outer",
                "v": "5.199",
                "object": {"user_id": 7, "peer_id": 8, "event_id": "inner", "payload": {}},
            }
        )
    )


async def test_concurrent_duplicates_run_handler_once(application: Application) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def callback(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    application.add_handler(Handler(callback))
    update = Update.from_dict(event())
    async with application, asyncio.timeout(2), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(application.process_update(update))
        await entered.wait()
        second = tasks.create_task(application.process_update(update))
        release.set()
    assert first.result() is True
    assert second.result() is False
    assert calls == 1


async def test_duplicate_cache_evicts_and_can_be_disabled(bot: Bot) -> None:
    application = Application(bot, 42, deduplication_size=1)
    first, second = Update.from_dict(event()), Update.from_dict(event("second"))
    async with application:
        assert await application.process_update(first)
        assert not await application.process_update(first)
        assert await application.process_update(second)
        assert await application.process_update(first)
    async with Application(bot, 42, deduplication_size=0) as uncached:
        assert await uncached.process_update(first)
        assert await uncached.process_update(first)


async def test_handler_failure_is_reported_safe_and_retryable(
    application: Application, caplog: pytest.LogCaptureFixture
) -> None:
    calls = 0
    errors: list[Exception | None] = []

    async def callback(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("private-message-content")

    async def broken_error_handler(update: Update | None, context: Context) -> None:
        raise RuntimeError("another-private-value")

    async def record_error(update: Update | None, context: Context) -> None:
        errors.append(context.error)

    application.add_handler(Handler(callback))
    application.add_error_handler(broken_error_handler)
    application.add_error_handler(record_error)
    update = Update.from_dict(event())
    async with application:
        with pytest.raises(ValueError, match="private-message-content"):
            await application.process_update(update)
        assert await application.process_update(update)
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert "private-message-content" not in caplog.text
    assert "another-private-value" not in caplog.text


async def test_cancelled_dispatch_is_retryable(application: Application) -> None:
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    calls = 0

    async def callback(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    application.add_handler(Handler(callback))
    update = Update.from_dict(event())
    async with application, asyncio.timeout(2):
        task = asyncio.create_task(application.process_update(update))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await application.process_update(update)
    assert cleaned.is_set()
    assert calls == 2


async def test_lifecycle_guards_and_recursive_dispatch(application: Application) -> None:
    update = Update.from_dict(event())
    with pytest.raises(LifecycleError, match="Initialize"):
        await application.start()
    with pytest.raises(LifecycleError, match="not running"):
        await application.process_update(update)

    async def callback(update: Update, context: Context) -> None:
        with pytest.raises(LifecycleError, match="Recursive"):
            await context.application.process_update(update)
        with pytest.raises(LifecycleError, match="Use stop"):
            await context.application.shutdown()

    application.add_handler(Handler(callback))
    async with application:
        with pytest.raises(LifecycleError, match="nested"):
            await application.__aenter__()
        with pytest.raises(LifecycleError, match="Register"):
            application.add_handler(Handler(callback))
        await application.process_update(update)
        foreign = event("foreign")
        foreign["group_id"] = 99
        with pytest.raises(ValueError, match="another community"):
            await application.process_update(Update.from_dict(foreign))
    assert not application.running


async def test_stop_drains_active_dispatch(application: Application) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def callback(update: Update, context: Context) -> None:
        entered.set()
        await release.wait()

    application.add_handler(Handler(callback))
    async with application, asyncio.timeout(2), asyncio.TaskGroup() as tasks:
        active = tasks.create_task(application.process_update(Update.from_dict(event())))
        await entered.wait()
        stopped = tasks.create_task(application.stop())
        await asyncio.sleep(0)
        assert not stopped.done()
        release.set()
    assert active.result() is True
    assert not application.running


async def test_polling_continues_after_handler_error_and_stops_from_handler(
    application: Application, api: MockAPI
) -> None:
    api.add(connection())
    api.add({"ts": "11", "updates": [event("bad"), event("good"), event("after-stop")]})
    calls: list[str] = []

    async def callback(update: Update, context: Context) -> None:
        calls.append(update.event_id)
        if update.event_id == "bad":
            raise ValueError("synthetic failure")
        await context.application.stop()

    application.add_handler(Handler(callback))
    async with asyncio.timeout(2):
        await application.run_polling()
    assert calls == ["bad", "good"]
    assert not application.running
    assert len(api.requests) == 2


@pytest.mark.parametrize("cancel_runner", [False, True])
async def test_polling_shutdown_interrupts_http(cancel_runner: bool) -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def pending(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.vk.ru":
            return httpx.Response(200, json=connection())
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        return httpx.Response(200, json={"ts": "11", "updates": []})

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(pending)) as client,
        asyncio.timeout(2),
    ):
        application = Application(Bot("placeholder", client=client), 42)
        runner = asyncio.create_task(application.run_polling())
        await entered.wait()
        if cancel_runner:
            runner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await runner
        else:
            await application.stop()
            await runner
        assert not client.is_closed
    assert cleaned.is_set()
    assert not application.running


async def test_polling_auth_error_reported_with_no_update(
    application: Application, api: MockAPI
) -> None:
    api.add({"error": {"error_code": 5, "error_msg": "unauthorized"}})
    seen: list[Update | None] = []

    async def callback(update: Update | None, context: Context) -> None:
        seen.append(update)
        assert isinstance(context.error, APIError)

    application.add_error_handler(callback)
    with pytest.raises(APIError):
        await application.run_polling()
    assert seen == [None]
    assert not application.running


@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_owned_client_closed_on_normal_and_failed_startup(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException] | None,
) -> None:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr("python_vk_bot.transport.httpx.AsyncClient", factory)
    hooks: list[str] = []

    async def startup(application: Application) -> None:
        hooks.append("startup")
        if failure is not None:
            raise failure("startup failed")

    async def shutdown(application: Application) -> None:
        hooks.append("shutdown")

    application = Application(Bot("placeholder"), 42, post_init=startup, post_shutdown=shutdown)
    if failure is not None:
        with pytest.raises(failure, match="startup failed"):
            async with application:
                pass
        assert hooks == ["startup"]
    else:
        async with application:
            assert application.running
        assert hooks == ["startup", "shutdown"]
    assert client.is_closed
    assert not application.running
