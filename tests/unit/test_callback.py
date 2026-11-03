import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import JsonValue

from python_vk_bot import (
    Application,
    ApplicationHandlerStop,
    Bot,
    Callback,
    Context,
    Handler,
    TypeHandler,
    Update,
)
from python_vk_bot.errors import CallbackAuthenticationError, LifecycleError

from .helpers import MockAPI, event

pytest.importorskip("starlette")


def authenticated_event(event_id: str = "event-1") -> dict[str, JsonValue]:
    return {**event(event_id), "secret": "synthetic-callback-secret"}


@pytest.fixture
def callback(application: Application) -> Callback:
    return Callback(
        application,
        secret="synthetic-callback-secret",  # noqa: S106 -- synthetic test credential
        confirmation_code="confirmation",
    )


@pytest.fixture
async def receiver(callback: Callback) -> AsyncIterator[httpx.AsyncClient]:
    app = callback.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        yield client


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "confirmation", "group_id": 42},
        {"type": "confirmation", "group_id": 42, "secret": "wrong"},
        {"type": "confirmation", "group_id": 99, "secret": "synthetic-callback-secret"},
        {"type": "confirmation", "group_id": True, "secret": "synthetic-callback-secret"},
    ],
)
async def test_confirmation_authentication(
    callback: Callback, payload: dict[str, JsonValue]
) -> None:
    with pytest.raises(CallbackAuthenticationError):
        await callback.handle(payload)


async def test_http_confirmation_and_plain_text_ack(receiver: httpx.AsyncClient) -> None:
    response = await receiver.post(
        "/callback",
        json={"type": "confirmation", "group_id": 42, "secret": "synthetic-callback-secret"},
    )
    assert response.status_code == 200
    assert response.text == "confirmation"
    assert response.headers["content-type"].startswith("text/plain")
    response = await receiver.post("/callback", json=authenticated_event())
    assert response.status_code == 200
    assert response.text == "ok"


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (b"invalid-json", 400),
        (b"[]", 400),
        (b"\xff", 400),
        (b'{"group_id":42,"secret":"wrong"}', 403),
        (b'{"group_id":42,"secret":"synthetic-callback-secret"}', 400),
    ],
)
async def test_http_bad_inputs(receiver: httpx.AsyncClient, body: bytes, status: int) -> None:
    response = await receiver.post("/callback", content=body)
    assert response.status_code == status
    assert "synthetic-callback-secret" not in response.text


async def test_failed_handler_returns_error_then_retry_succeeds(
    application: Application, callback: Callback
) -> None:
    calls = 0

    async def handler(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        assert "secret" not in update.model_dump()
        if calls == 1:
            raise ValueError("private-handler-error")

    application.add_handler(Handler(handler))
    app = callback.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        first = await client.post("/callback", json=authenticated_event())
        retry = await client.post("/callback", json=authenticated_event())
        duplicate = await client.post("/callback", json=authenticated_event())
    assert first.status_code == 500
    assert "private-handler-error" not in first.text
    assert retry.status_code == 200
    assert duplicate.text == "ok"
    assert calls == 2
    assert not application.running


async def test_concurrent_duplicate_is_acknowledged_after_first(
    application: Application, callback: Callback
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def handler(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    application.add_handler(Handler(handler))
    app = callback.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
        asyncio.timeout(2),
        asyncio.TaskGroup() as tasks,
    ):
        first = tasks.create_task(client.post("/callback", json=authenticated_event()))
        await entered.wait()
        second = tasks.create_task(client.post("/callback", json=authenticated_event()))
        await asyncio.sleep(0)
        assert not second.done()
        release.set()
    assert first.result().text == "ok"
    assert second.result().text == "ok"
    assert calls == 1


async def test_body_limit_applies_to_streamed_requests(callback: Callback) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * 8
        yield b"x" * 8

    app = callback.create_app(max_body_bytes=10)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        response = await client.post("/callback", content=chunks())
    assert response.status_code == 413


async def test_overload_rejected_and_capacity_released(
    application: Application, callback: Callback
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(update: Update, context: Context) -> None:
        entered.set()
        await release.wait()

    application.add_handler(Handler(handler))
    app = callback.create_app(max_pending=1)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
        asyncio.timeout(2),
        asyncio.TaskGroup() as tasks,
    ):
        active = tasks.create_task(client.post("/callback", json=authenticated_event()))
        await entered.wait()
        overloaded = await client.post("/callback", json=authenticated_event("second"))
        assert overloaded.status_code == 503
        release.set()
        await active
        recovered = await client.post("/callback", json=authenticated_event("third"))
        assert recovered.text == "ok"


async def test_request_timeout_cancels_handler_and_releases_capacity(
    application: Application, callback: Callback
) -> None:
    cleaned = asyncio.Event()
    calls = 0

    async def handler(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    application.add_handler(Handler(handler))
    app = callback.create_app(max_pending=1, request_timeout=0.02)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
        asyncio.timeout(2),
    ):
        timed_out = await client.post("/callback", json=authenticated_event())
        assert timed_out.status_code == 503
        assert cleaned.is_set()
        retried = await client.post("/callback", json=authenticated_event())
        assert retried.text == "ok"
    assert calls == 2


async def test_missing_lifespan_does_not_process_events(callback: Callback) -> None:
    app = callback.create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
    ) as client:
        response = await client.post("/callback", json=authenticated_event())
    assert response.status_code == 503


@pytest.mark.parametrize("before_admission", [False, True])
async def test_http_timeout_while_queued_or_waiting_for_capacity_is_retryable(
    bot: Bot, before_admission: bool
) -> None:
    application = Application(bot, 42, update_queue_size=1)
    callback = Callback(
        application,
        secret="synthetic-callback-secret",  # noqa: S106 -- synthetic test credential
        confirmation_code="confirmation",
    )
    entered, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def hold(value: str, context: Context) -> None:
        if value == "gate":
            entered.set()
            await release.wait()

    async def handler(update: Update, context: Context) -> None:
        calls.append(update.event_id)

    application.add_handler(TypeHandler(str, hold))
    application.add_handler(Handler(handler))
    app = callback.create_app(request_timeout=0.02)
    async with (
        asyncio.timeout(2),
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        await application.update_queue.put("gate")
        try:
            await entered.wait()
            if before_admission:
                application.update_queue.put_nowait("queued")
            response = await client.post("/callback", json=authenticated_event())
            assert response.status_code == 503
            assert calls == []
            assert application.update_queue.full()
            forbidden = await client.post(
                "/callback", json={**authenticated_event(), "secret": "wrong"}
            )
            assert forbidden.status_code == 403
            confirmation = await client.post(
                "/callback",
                json={
                    "type": "confirmation",
                    "group_id": 42,
                    "secret": "synthetic-callback-secret",
                },
            )
            assert confirmation.text == "confirmation"
        finally:
            release.set()
        retry = await client.post("/callback", json=authenticated_event())
        duplicate = await client.post("/callback", json=authenticated_event())
        assert retry.text == duplicate.text == "ok"
    assert calls == ["event-1"]


async def test_http_handler_stop_acknowledges_and_deduplicates(
    application: Application, callback: Callback
) -> None:
    calls: list[str] = []

    async def handler(update: Update, context: Context) -> None:
        calls.append(update.event_id)
        raise ApplicationHandlerStop

    async def skipped(update: Update, context: Context) -> None:
        calls.append("skipped")

    async def error_handler(update: Update | None, context: Context) -> None:
        calls.append("error")

    application.add_handler(Handler(handler), group=-1)
    application.add_handler(Handler(skipped))
    application.add_error_handler(error_handler)
    app = callback.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        for event_id in ("first", "first", "second"):
            response = await client.post("/callback", json=authenticated_event(event_id))
            assert response.status_code == 200
            assert response.text == "ok"
    assert calls == ["first", "second"]


async def test_asgi_lifespan_drains_results_before_post_stop(bot: Bot, api: MockAPI) -> None:
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def stopped(application: Application) -> None:
        assert calls == ["computed", "result"]
        await application.bot.send_message(7, "shutdown notification")
        calls.append("post_stop")

    async def shutdown(application: Application) -> None:
        with pytest.raises(LifecycleError, match="Initialize"):
            await application.bot.send_message(7, "too late")
        calls.append("post_shutdown")

    application = Application(bot, 42, post_stop=stopped, post_shutdown=shutdown)

    async def compute() -> None:
        started.set()
        await release.wait()
        calls.append("computed")
        await application.update_queue.put(1)

    async def handler(update: Update, context: Context) -> None:
        application.create_task(compute(), update=update)

    async def result_handler(value: int, context: Context) -> None:
        calls.append("result")

    application.add_handler(Handler(handler))
    application.add_handler(TypeHandler(int, result_handler))
    callback = Callback(
        application,
        secret="synthetic-callback-secret",  # noqa: S106 -- synthetic test credential
        confirmation_code="confirmation",
    )
    api.add({"response": 10})
    app = callback.create_app()
    before = asyncio.all_tasks()
    async with (
        asyncio.timeout(2),
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
    ):
        try:
            response = await client.post("/callback", json=authenticated_event())
            await started.wait()
            assert response.text == "ok"
            assert calls == []
        finally:
            release.set()
    await application.shutdown()
    assert calls == ["computed", "result", "post_stop", "post_shutdown"]
    assert len(api.requests) == 1
    assert asyncio.all_tasks() == before
