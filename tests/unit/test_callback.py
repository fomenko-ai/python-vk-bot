from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import JsonValue

from python_vk_bot import Application, Callback, Context, Handler, Update
from python_vk_bot.errors import CallbackAuthenticationError

from .helpers import event, running_task, timeout

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
        timeout(2),
        running_task(client.post("/callback", json=authenticated_event())) as first,
    ):
        await entered.wait()
        async with running_task(client.post("/callback", json=authenticated_event())) as second:
            await asyncio.sleep(0)
            assert not second.done()
            release.set()
            assert (await first).text == "ok"
            assert (await second).text == "ok"
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
        timeout(2),
        running_task(client.post("/callback", json=authenticated_event())) as active,
    ):
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
        timeout(2),
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


async def test_external_cancellation_releases_capacity_and_allows_retry(
    application: Application, callback: Callback
) -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()
    calls = 0

    async def handler(update: Update, context: Context) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    application.add_handler(Handler(handler))
    app = callback.create_app(max_pending=1)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://callback.example"
        ) as client,
        timeout(2),
    ):
        async with running_task(client.post("/callback", json=authenticated_event())) as request:
            await entered.wait()
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        assert cleaned.is_set()
        retried = await client.post("/callback", json=authenticated_event())
        assert retried.status_code == 200
        assert retried.text == "ok"
    assert calls == 2
