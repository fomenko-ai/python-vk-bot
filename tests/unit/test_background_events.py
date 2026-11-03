from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass

import pytest

from python_vk_bot import (
    Application,
    ApplicationHandlerStop,
    Bot,
    Context,
    Handler,
    TypeHandler,
    Update,
    filters,
)
from python_vk_bot.errors import LifecycleError

from .helpers import event, running_task, timeout


@dataclass(frozen=True)
class Result:
    value: str


class SpecializedResult(Result):
    pass


@pytest.mark.parametrize(("strict", "expected"), [(False, 2), (True, 1)])
async def test_type_handler_matching_and_vk_filter_isolation(
    application: Application, strict: bool, expected: int
) -> None:
    matches: list[Result] = []
    filtered: list[Update] = []

    def vk_filter(update: Update) -> bool:
        assert isinstance(update, Update)
        filtered.append(update)
        return True

    async def vk_handler(update: Update, context: Context) -> None:
        assert context.event is update

    async def result_handler(result: Result, context: Context) -> None:
        assert context.event is result
        matches.append(result)

    application.add_handler(Handler(vk_handler, predicate=filters.Filter(vk_filter)))
    application.add_handler(TypeHandler(Result, result_handler, strict=strict))
    update = Update.from_dict(event())
    async with application:
        await application.process_update(Result("base"))
        await application.process_update(SpecializedResult("child"))
        await application.process_update(update)
    assert len(matches) == expected
    assert filtered == [update]


async def test_vk_and_internal_events_share_serial_fifo(application: Application) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    seen: list[object] = []
    active = 0
    update = Update.from_dict(event())
    result = Result("computed")
    payload = {"event_id": update.event_id, "group_id": 999}

    async def handler(value: object, context: Context) -> None:
        nonlocal active
        active += 1
        assert active == 1
        if value == "gate":
            entered.set()
            await release.wait()
        seen.append(value)
        active -= 1

    application.add_handler(TypeHandler(object, handler))
    async with timeout(2), application:
        application.update_queue.put_nowait("gate")
        try:
            await entered.wait()
            await application.update_queue.put(result)
            await application.update_queue.put(update)
            await application.update_queue.put(payload)
            await application.update_queue.put(payload)
            assert seen == []
        finally:
            release.set()
        assert await application.process_update("barrier")
        assert not await application.process_update(update)
    assert seen == ["gate", result, update, payload, payload, "barrier"]


async def test_internal_state_is_explicit_and_errors_keep_scopes(application: Application) -> None:
    contexts: list[Context] = []
    errors: list[tuple[Update | None, Context]] = []
    update = Update.from_dict(event(user_id=7, peer_id=8))
    # Similar-looking attributes must not implicitly select VK state or deduplication.
    internal = {"user_id": 7, "peer_id": 8, "event_id": update.event_id, "group_id": 42}

    async def handler(value: object, context: Context) -> None:
        contexts.append(context)
        if value == "failure":
            raise ValueError("synthetic failure")

    async def error_handler(value: Update | None, context: Context) -> None:
        errors.append((value, context))

    application.add_handler(TypeHandler(object, handler))
    application.add_error_handler(error_handler)
    async with application:
        await application.process_update(update)
        await application.process_update(internal)
        await application.process_update(internal)
        await application.process_update(internal, user_id=7, peer_id=8)
        with pytest.raises(ValueError, match="synthetic failure"):
            await application.process_update("failure", user_id=7, peer_id=8)
    assert contexts[1].user_data == contexts[1].peer_data == {}
    assert contexts[1].user_data is not contexts[2].user_data
    assert contexts[1].peer_data is not contexts[2].peer_data
    assert contexts[3].user_data is contexts[0].user_data is application.user_data[7]
    assert contexts[3].peer_data is contexts[0].peer_data is application.peer_data[8]
    assert all(context.bot_data is application.bot_data for context in contexts)
    assert errors[0][0] is None
    assert errors[0][1].event == "failure"
    assert errors[0][1].user_data is application.user_data[7]
    assert errors[0][1].peer_data is application.peer_data[8]


@pytest.mark.parametrize("internal", [False, True])
async def test_handler_stop_is_success_and_only_stops_current_event(
    application: Application, internal: bool
) -> None:
    first: object = Result("first") if internal else Update.from_dict(event("first"))
    second: object = Result("second") if internal else Update.from_dict(event("second"))
    calls: list[tuple[str, object]] = []
    errors: list[Exception | None] = []

    async def route(value: object, context: Context) -> None:
        calls.append(("route", value))
        if value is first:
            raise ApplicationHandlerStop

    async def later(value: object, context: Context) -> None:
        calls.append(("later", value))

    async def error_handler(update: Update | None, context: Context) -> None:
        errors.append(context.error)

    application.add_handler(TypeHandler(object, route), group=-1)
    application.add_handler(TypeHandler(object, later))
    application.add_error_handler(error_handler)
    async with application:
        assert await application.process_update(first)
        assert await application.process_update(second)
        assert calls == [("route", first), ("route", second), ("later", second)]
        assert await application.process_update(first) is internal
    assert errors == []


async def test_error_handler_stop_preserves_original_failure_and_retry(
    application: Application,
) -> None:
    error = ValueError("original")
    calls: list[str] = []

    async def handler(update: Update, context: Context) -> None:
        calls.append("handler")
        raise error

    async def stop_errors(update: Update | None, context: Context) -> None:
        calls.append("error")
        assert context.error is error
        raise ApplicationHandlerStop

    async def skipped(update: Update | None, context: Context) -> None:
        calls.append("skipped")

    application.add_handler(Handler(handler))
    application.add_error_handler(stop_errors)
    application.add_error_handler(skipped)
    async with application:
        for _ in range(2):
            with pytest.raises(ValueError, match="original") as caught:
                await application.process_update(Update.from_dict(event()))
            assert caught.value is error
    assert calls == ["handler", "error"] * 2


async def test_queued_internal_error_is_reported_once_and_consumer_continues(
    application: Application, caplog: pytest.LogCaptureFixture
) -> None:
    error = ValueError("private-event-content")
    seen: list[str] = []
    errors: list[Exception | None] = []

    async def handler(value: str, context: Context) -> None:
        if value == "bad":
            raise error
        seen.append(value)

    async def error_handler(update: Update | None, context: Context) -> None:
        assert update is None
        assert context.event == "bad"
        errors.append(context.error)

    application.add_handler(TypeHandler(str, handler))
    application.add_error_handler(error_handler)
    async with application:
        await application.update_queue.put("bad")
        await application.process_update("good")
    assert errors == [error]
    assert seen == ["good"]
    assert "private-event-content" not in caplog.text


@pytest.mark.parametrize("maxsize", [0, -1])
def test_queue_requires_positive_capacity(bot: Bot, maxsize: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        Application(bot, 42, update_queue_size=maxsize)


async def test_foreign_updates_and_vk_scope_overrides_are_rejected(
    application: Application,
) -> None:
    payload = event()
    payload["group_id"] = 99
    foreign = Update.from_dict(payload)
    update = Update.from_dict(event())
    async with application:
        with pytest.raises(ValueError, match="another community"):
            await application.update_queue.put(foreign)
        with pytest.raises(ValueError, match="state scopes"):
            application.update_queue.put_nowait(update, user_id=7)
        with pytest.raises(ValueError, match="state scopes"):
            await application.process_update(update, peer_id=8)
        assert application.update_queue.empty()
        assert await application.process_update(update)


async def test_full_queue_never_blocks_its_own_handler(bot: Bot) -> None:
    application = Application(bot, 42, update_queue_size=1)
    seen: list[str] = []

    async def handler(value: str, context: Context) -> None:
        seen.append(value)
        if value == "first":
            application.update_queue.put_nowait("second")
            assert application.update_queue.full()
            with pytest.raises(asyncio.QueueFull):
                await application.update_queue.put("never")
            with pytest.raises(asyncio.QueueFull):
                application.update_queue.put_nowait("never")
            with pytest.raises(LifecycleError, match="Recursive"):
                await application.process_update("never")

    application.add_handler(TypeHandler(str, handler))
    async with timeout(2), application:
        assert application.update_queue.maxsize == 1
        await application.process_update("first")
    assert seen == ["first", "second"]
    assert application.update_queue.empty()


@pytest.mark.parametrize("stopping", [False, True])
async def test_waiting_producer_wakes_on_capacity_or_stop(bot: Bot, stopping: bool) -> None:
    application = Application(bot, 42, update_queue_size=1)
    entered, release, producing = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen: list[str] = []

    async def handler(value: str, context: Context) -> None:
        if value == "active":
            entered.set()
            await release.wait()
        seen.append(value)

    async def producer() -> None:
        producing.set()
        await application.update_queue.put("produced")

    application.add_handler(TypeHandler(str, handler))
    async with timeout(2), application:
        await application.update_queue.put("active")
        await entered.wait()
        application.update_queue.put_nowait("queued")
        task = asyncio.create_task(producer())
        try:
            await producing.wait()
            assert not task.done()
            assert application.update_queue.qsize() == 1
            if stopping:
                stop = asyncio.create_task(application.stop())
                with pytest.raises(LifecycleError, match="not running"):
                    await task
                assert not stop.done()
                release.set()
                await stop
            else:
                release.set()
                await task
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert seen == (["active", "queued"] if stopping else ["active", "queued", "produced"])


async def test_finite_task_publishes_during_stop_before_consumer_exits(
    application: Application,
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    seen: list[Result] = []

    async def compute() -> int:
        entered.set()
        await release.wait()
        await application.update_queue.put(Result("finished"))
        return 42

    async def handler(result: Result, context: Context) -> None:
        seen.append(result)
        with pytest.raises(LifecycleError, match="not running"):
            await application.update_queue.put(Result("too late"))

    application.add_handler(TypeHandler(Result, handler))
    before = asyncio.all_tasks()
    async with timeout(2), application:
        task = application.create_task(compute(), name="finite-computation")
        await entered.wait()
        stop = asyncio.create_task(application.stop())
        try:
            await asyncio.sleep(0)
            assert not application.running
            assert not stop.done()
        finally:
            release.set()
        await stop
        assert task.result() == 42
        assert seen == [Result("finished")]
    assert asyncio.all_tasks() == before


async def test_worker_cancellation_drains_final_result_and_does_not_report_error(
    application: Application,
) -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()
    seen: list[str] = []
    errors: list[Exception | None] = []

    async def worker() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            await application.update_queue.put("final result")
            cleaned.set()

    async def handler(value: str, context: Context) -> None:
        seen.append(value)

    async def error_handler(update: Update | None, context: Context) -> None:
        errors.append(context.error)

    application.add_handler(TypeHandler(str, handler))
    application.add_error_handler(error_handler)
    before = asyncio.all_tasks()
    async with timeout(2), application:
        task = application.create_task(worker(), cancel_on_stop=True)
        await entered.wait()
    assert cleaned.is_set()
    assert task.cancelled()
    assert seen == ["final result"]
    assert errors == []
    assert asyncio.all_tasks() == before


@pytest.mark.parametrize("origin", [None, Result("origin"), Update.from_dict(event())])
@pytest.mark.parametrize("failure", [ValueError, ApplicationHandlerStop])
async def test_task_failure_reports_origin_and_remains_on_task(
    application: Application, origin: object, failure: type[Exception]
) -> None:
    errors: list[Context] = []
    error = failure("synthetic task failure")

    async def compute() -> None:
        raise error

    async def error_handler(update: Update | None, context: Context) -> None:
        assert update is (origin if isinstance(origin, Update) else None)
        assert context.event is origin
        errors.append(context)

    application.add_error_handler(error_handler)
    async with timeout(2), application:
        task = application.create_task(compute(), update=origin)
        with pytest.raises(failure) as caught:
            await task
        assert caught.value is error
        assert task.exception() is error
        assert [context.error for context in errors] == [error]
        if isinstance(origin, Update):
            assert errors[0].user_data is application.user_data[7]
        else:
            assert errors[0].user_data == errors[0].peer_data == {}
        assert await application.process_update("next event")


async def test_task_error_callback_waits_for_current_handler(application: Application) -> None:
    entered, release, failed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def handler(value: str, context: Context) -> None:
        calls.append("handler entered")
        entered.set()
        await release.wait()
        calls.append("handler exited")

    async def compute() -> None:
        failed.set()
        raise ValueError("failed computation")

    async def error_handler(update: Update | None, context: Context) -> None:
        calls.append("error callback")

    application.add_handler(TypeHandler(str, handler))
    application.add_error_handler(error_handler)
    async with timeout(2), application:
        await application.update_queue.put("active")
        await entered.wait()
        task = application.create_task(compute())
        try:
            await failed.wait()
            assert calls == ["handler entered"]
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(ValueError, match="failed computation"):
            await task
    assert calls == ["handler entered", "handler exited", "error callback"]


async def test_task_admission_and_coroutine_ownership(application: Application) -> None:
    async def compute() -> int:
        return 5

    async def reject_task() -> None:
        coroutine = compute()
        with pytest.raises(LifecycleError, match="only while"):
            application.create_task(coroutine)
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED

    await reject_task()
    with pytest.raises(LifecycleError):
        await application.update_queue.put("before start")
    async with application:
        coroutine = compute()
        task = application.create_task(coroutine)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED
        payload = event()
        payload["group_id"] = 99
        coroutine = compute()
        with pytest.raises(ValueError, match="another community"):
            application.create_task(coroutine, update=Update.from_dict(payload))
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED
        await application.stop()
        await reject_task()
    await reject_task()
    with pytest.raises(LifecycleError):
        application.update_queue.put_nowait("after shutdown")


async def test_managed_task_can_request_stop_without_waiting_for_itself(
    application: Application,
) -> None:
    async def compute() -> int:
        with pytest.raises(LifecycleError, match="Use stop"):
            await application.shutdown()
        await application.stop()
        await application.update_queue.put(Result("last"))
        return 7

    async with timeout(2), application:
        task = application.create_task(compute())
        assert await task == 7
        await application.stop()
    assert not application.running


async def test_active_handler_can_publish_after_requesting_stop(application: Application) -> None:
    seen: list[str] = []

    async def handler(value: str, context: Context) -> None:
        seen.append(value)
        if value == "active":
            await application.stop()
            await application.update_queue.put("last")
        else:
            with pytest.raises(LifecycleError):
                await application.update_queue.put("rejected")

    application.add_handler(TypeHandler(str, handler))
    async with timeout(2), application:
        assert await application.process_update("active")
    assert seen == ["active", "last"]


async def test_managed_producer_waiting_for_capacity_finishes_during_stop(bot: Bot) -> None:
    application = Application(bot, 42, update_queue_size=1)
    entered, release, producing = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen: list[str] = []

    async def handler(value: str, context: Context) -> None:
        if value == "active":
            entered.set()
            await release.wait()
        seen.append(value)

    async def producer() -> None:
        producing.set()
        await application.update_queue.put("result")

    application.add_handler(TypeHandler(str, handler))
    async with timeout(2), application:
        application.update_queue.put_nowait("active")
        await entered.wait()
        application.update_queue.put_nowait("queued")
        task = application.create_task(producer())
        try:
            await producing.wait()
            assert not task.done()
            stop = asyncio.create_task(application.stop())
            await asyncio.sleep(0)
            assert not application.running
            assert not stop.done()
        finally:
            release.set()
        await stop
        assert task.done()
        assert not task.cancelled()
    assert seen == ["active", "queued", "result"]


async def test_task_error_handler_can_request_stop(application: Application) -> None:
    calls: list[str] = []

    async def compute() -> None:
        raise ValueError("failed task")

    async def error_handler(update: Update | None, context: Context) -> None:
        calls.append("error")
        await application.stop()
        calls.append("stop requested")

    application.add_error_handler(error_handler)
    async with timeout(2), application:
        task = application.create_task(compute())
        with pytest.raises(ValueError, match="failed task"):
            await task
        await application.stop()
    assert calls == ["error", "stop requested"]


async def test_post_init_cannot_start_tasks_or_enqueue_events(bot: Bot) -> None:
    async def compute() -> None:
        raise AssertionError("Rejected coroutine must not run")

    async def initialized(application: Application) -> None:
        coroutine = compute()
        with pytest.raises(LifecycleError, match="only while"):
            application.create_task(coroutine)
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED
        with pytest.raises(LifecycleError):
            await application.update_queue.put("before start")

    async with timeout(2), Application(bot, 42, post_init=initialized):
        pass


@pytest.mark.parametrize("queued", [False, True])
async def test_private_close_wakes_consumer_and_drains_fifo(bot: Bot, queued: bool) -> None:
    application = Application(bot, 42, update_queue_size=2)
    from python_vk_bot.queues import _QueueItem

    queue = application.update_queue
    values = ["first", "second"] if queued else []
    for value in values:
        queue._queue.put_nowait(_QueueItem(value))

    async def consume() -> list[object]:
        from python_vk_bot.queues import _QueueClosed

        received: list[object] = []
        while True:
            try:
                item = await queue._get()
            except _QueueClosed:
                return received
            received.append(item.event)
            queue._queue.task_done()

    if queued:
        assert queue.full()
        queue._close()
    async with timeout(2), running_task(consume()) as consumer:
        if not queued:
            await asyncio.sleep(0)
            assert not consumer.done()
            queue._close()
        assert await consumer == values
    assert queue.empty()
