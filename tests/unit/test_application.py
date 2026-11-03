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
    TypeHandler,
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

    async def stopped(application: Application) -> None:
        hooks.append("stop")

    application = Application(
        Bot("placeholder"), 42, post_init=startup, post_stop=stopped, post_shutdown=shutdown
    )
    if failure is not None:
        with pytest.raises(failure, match="startup failed"):
            async with application:
                pass
        assert hooks == ["startup"]
    else:
        async with application:
            assert application.running
        assert hooks == ["startup", "stop", "shutdown"]
    assert client.is_closed
    assert not application.running


@pytest.mark.parametrize("mode", ["manual", "context", "polling"])
async def test_post_stop_order_and_bot_availability(bot: Bot, api: MockAPI, mode: str) -> None:
    calls: list[str] = []

    async def initialized(application: Application) -> None:
        calls.append("init")

    async def stopped(application: Application) -> None:
        assert not application.running
        assert await application.bot.send_message(7, "final message") == 100
        calls.append("post_stop")

    async def shutdown(application: Application) -> None:
        with pytest.raises(LifecycleError, match="Initialize"):
            await application.bot.send_message(7, "too late")
        calls.append("post_shutdown")

    async def handler(update: Update, context: Context) -> None:
        calls.append("handler")
        await context.application.stop()

    application = Application(
        bot, 42, post_init=initialized, post_stop=stopped, post_shutdown=shutdown
    )
    application.add_handler(Handler(handler))
    if mode == "polling":
        api.add(connection())
        api.add({"ts": "11", "updates": [event()]})
    api.add({"response": 100})
    async with asyncio.timeout(2):
        if mode == "polling":
            await application.run_polling()
        elif mode == "context":
            async with application:
                await application.process_update(Update.from_dict(event()))
        else:
            await application.initialize()
            await application.start()
            try:
                await application.process_update(Update.from_dict(event()))
                await application.stop()
                assert calls == ["init", "handler"]
            finally:
                await application.shutdown()
        await application.stop()
        await application.shutdown()
    assert calls == ["init", "handler", "post_stop", "post_shutdown"]


@pytest.mark.parametrize("failure", [ValueError, asyncio.CancelledError])
async def test_failed_post_stop_still_closes_owned_bot_and_runs_post_shutdown_once(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: type[BaseException],
) -> None:
    def factory(**kwargs: object) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr("python_vk_bot.transport.httpx.AsyncClient", factory)
    calls: list[str] = []

    async def stopped(application: Application) -> None:
        calls.append("post_stop")
        assert not client.is_closed
        raise failure("private-stop-error")

    async def shutdown(application: Application) -> None:
        calls.append("post_shutdown")
        assert client.is_closed
        raise RuntimeError("private-shutdown-error")

    application = Application(Bot("placeholder"), 42, post_stop=stopped, post_shutdown=shutdown)
    async with asyncio.timeout(2):
        with pytest.raises(failure):
            async with application:
                pass
        with pytest.raises(failure):
            await application.shutdown()
    assert client.is_closed
    assert calls == ["post_stop", "post_shutdown"]
    assert "private-stop-error" not in caplog.text
    assert "private-shutdown-error" not in caplog.text


async def test_body_error_is_preserved_when_cleanup_also_fails(
    bot: Bot, caplog: pytest.LogCaptureFixture
) -> None:
    original = LookupError("private-body-error")

    async def stopped(application: Application) -> None:
        raise ValueError("private-cleanup-error")

    async with asyncio.timeout(2):
        with pytest.raises(LookupError) as caught:
            async with Application(bot, 42, post_stop=stopped):
                raise original
    assert caught.value is original
    with pytest.raises(LifecycleError, match="Initialize"):
        await bot.send_message(7, "after cleanup")
    assert "private-body-error" not in caplog.text
    assert "private-cleanup-error" not in caplog.text


@pytest.mark.parametrize("phase", ["post_init", "post_stop", "post_shutdown"])
async def test_lifecycle_hook_reentry_fails_without_deadlocking(bot: Bot, phase: str) -> None:
    calls: list[str] = []

    async def hook(application: Application) -> None:
        for method in (
            application.initialize,
            application.start,
            application.stop,
            application.shutdown,
        ):
            with pytest.raises(LifecycleError, match="recursively"):
                await method()
            calls.append(method.__name__)

    application = Application(
        bot,
        42,
        post_init=hook if phase == "post_init" else None,
        post_stop=hook if phase == "post_stop" else None,
        post_shutdown=hook if phase == "post_shutdown" else None,
    )
    async with asyncio.timeout(2), application:
        pass
    assert calls == ["initialize", "start", "stop", "shutdown"]


async def test_repeated_shutdown_cancellation_waits_for_cleanup(bot: Bot, api: MockAPI) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def stopped(application: Application) -> None:
        calls.append("entered")
        entered.set()
        await release.wait()
        assert await application.bot.send_message(7, "finishing") == 10
        calls.append("finished")

    application = Application(bot, 42, post_stop=stopped)
    api.add({"response": 10})
    before = asyncio.all_tasks()
    async with asyncio.timeout(2):
        await application.initialize()
        await application.start()
        owner = asyncio.create_task(application.shutdown())
        observer = asyncio.create_task(application.shutdown())
        try:
            await entered.wait()
            owner.cancel()
            await asyncio.sleep(0)
            owner.cancel()
            await asyncio.sleep(0)
            assert not owner.done()
            assert not observer.done()
            assert calls == ["entered"]
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        await observer
        await application.shutdown()
    assert calls == ["entered", "finished"]
    with pytest.raises(LifecycleError, match="Initialize"):
        await bot.send_message(7, "too late")
    assert asyncio.all_tasks() == before


async def test_restart_requires_full_lifecycle_and_rejects_stale_queue(bot: Bot) -> None:
    calls: list[str] = []
    seen: list[str] = []

    async def stopped(application: Application) -> None:
        calls.append("stop")

    async def handler(value: str, context: Context) -> None:
        seen.append(value)

    application = Application(bot, 42, post_stop=stopped)
    application.add_handler(TypeHandler(str, handler))
    first_queue = application.update_queue
    async with asyncio.timeout(2), application:
        assert application.update_queue is first_queue
        await application.start()
        await application.process_update("first")
        await application.stop()
        with pytest.raises(LifecycleError, match="Shut down"):
            await application.start()
        with pytest.raises(LifecycleError, match="Register"):
            application.add_handler(TypeHandler(str, handler))
        assert calls == []
    assert calls == ["stop"]
    async with application:
        assert application.update_queue is not first_queue
        with pytest.raises(LifecycleError):
            first_queue.put_nowait("stale")
        await application.process_update("second")
    assert seen == ["first", "second"]
    assert calls == ["stop", "stop"]


@pytest.mark.parametrize("cancel_runner", [False, True])
async def test_polling_active_dispatch_graceful_stop_or_cancellation(
    bot: Bot, api: MockAPI, cancel_runner: bool
) -> None:
    entered, release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def handler(update: Update, context: Context) -> None:
        entered.set()
        try:
            await release.wait()
            calls.append("handled")
        finally:
            cleaned.set()

    async def stopped(application: Application) -> None:
        assert cleaned.is_set()
        calls.append("post_stop")

    application = Application(bot, 42, post_stop=stopped)
    application.add_handler(Handler(handler))
    api.add(connection())
    api.add({"ts": "11", "updates": [event(), event("after-stop")]})
    before = asyncio.all_tasks()
    async with asyncio.timeout(2):
        runner = asyncio.create_task(application.run_polling())
        try:
            await entered.wait()
            if cancel_runner:
                runner.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await runner
            else:
                stop = asyncio.create_task(application.stop())
                await asyncio.sleep(0)
                assert not stop.done()
                assert not cleaned.is_set()
                release.set()
                await stop
                await runner
        finally:
            release.set()
            if not runner.done():
                runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)
    assert calls == (["post_stop"] if cancel_runner else ["handled", "post_stop"])
    assert asyncio.all_tasks() == before


async def test_repeated_event_cancellation_waits_for_handler_cleanup(
    application: Application,
) -> None:
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = 0

    async def handler(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

    application.add_handler(Handler(handler))
    update = Update.from_dict(event())
    async with asyncio.timeout(2), application:
        task = asyncio.create_task(application.process_update(update))
        try:
            await entered.wait()
            task.cancel()
            await cleaning.wait()
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await application.process_update(update)
    assert calls == 2


@pytest.mark.parametrize("stop_first", [True, False])
async def test_stop_and_runner_cancellation_share_polling_cleanup(stop_first: bool) -> None:
    entered, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def pending(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.vk.ru":
            return httpx.Response(200, json=connection())
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()
        return httpx.Response(200, json={"ts": "11", "updates": []})

    before = asyncio.all_tasks()
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(pending)) as client,
        asyncio.timeout(2),
    ):
        application = Application(Bot("placeholder", client=client), 42)
        async with asyncio.TaskGroup() as runners:
            runner = runners.create_task(application.run_polling())
            try:
                await entered.wait()
                if not stop_first:
                    runner.cancel()
                    await cleaning.wait()
                async with asyncio.TaskGroup() as stoppers:
                    stopping = stoppers.create_task(application.stop())
                    try:
                        if stop_first:
                            await cleaning.wait()
                            runner.cancel()
                        # Let both owners reach their wait for the blocked cleanup.
                        for _ in range(5):
                            await asyncio.sleep(0)
                        runner.cancel()
                        for _ in range(5):
                            await asyncio.sleep(0)
                        assert not runner.done()
                        assert not stopping.done()
                        assert not cleaned.is_set()
                    finally:
                        release.set()
                    with pytest.raises(asyncio.CancelledError):
                        await runner
                    await stopping
            finally:
                release.set()
        assert cleaned.is_set()
        assert not application.running
        assert not client.is_closed
    assert asyncio.all_tasks() == before
