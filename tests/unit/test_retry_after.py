"""Retry-After at the HTTP boundary; no real network requests or delays."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import SecretStr

from python_vk_bot import Bot, transport
from python_vk_bot.errors import HTTPError, RateLimitError

from .helpers import MockAPI


@pytest.fixture(autouse=True)
def freeze_utc_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(transport, "datetime", clock)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param("120", 120.0, id="seconds"),
        pytest.param("0", 0.0, id="zero"),
        pytest.param(" \t0030\t ", 30.0, id="whitespace-and-leading-zeroes"),
        pytest.param("Fri, 06 Nov 2026 12:00:30 GMT", 30.0, id="http-date"),
        pytest.param("Friday, 06-Nov-26 12:00:30 GMT", 30.0, id="obsolete-rfc850"),
        pytest.param("Fri Nov  6 12:00:30 2026", 30.0, id="obsolete-asctime"),
        pytest.param("Fri, 06 Nov 2026 11:59:59 GMT", 0.0, id="past-date"),
        pytest.param("Fri, 06 Nov 2026 12:00:00 GMT", 0.0, id="current-date"),
        pytest.param(None, None, id="missing"),
        pytest.param("", None, id="empty"),
        pytest.param(" \t", None, id="whitespace"),
        pytest.param("later", None, id="invalid"),
        pytest.param("-1", None, id="negative"),
        pytest.param("+1", None, id="signed"),
        pytest.param("1.5", None, id="fraction"),
        pytest.param("1e2", None, id="exponent"),
        pytest.param("NaN", None, id="nan"),
        pytest.param("inf", None, id="infinity"),
        pytest.param("9" * 400, None, id="overflow"),
        pytest.param("Fri, 31 Nov 2026 12:00:30 GMT", None, id="invalid-day"),
        pytest.param("Fri, 06 Nov 2026 25:00:30 GMT", None, id="invalid-hour"),
        pytest.param("Sat, 06 Nov 0000 12:00:30 GMT", None, id="invalid-year-zero"),
        pytest.param("Tue, 06 Nov 0068 12:00:30 GMT", 0.0, id="four-digit-early-year"),
        pytest.param("Sat Nov  6 12:00:30 0000", None, id="asctime-invalid-year-zero"),
        pytest.param("Tue Nov  6 12:00:30 0068", 0.0, id="asctime-four-digit-early-year"),
        pytest.param("Fri, 06 Nov 2026 12:00:30", None, id="missing-timezone"),
        pytest.param("Fri, 06 Nov 2026 12:00:30 GMT garbage", None, id="trailing-garbage"),
        pytest.param("120, 240", None, id="combined-values"),
    ],
)
async def test_retry_after_is_read_from_error_response(
    bot: Bot, api: MockAPI, header: str | None, expected: float | None
) -> None:
    headers = {"rEtRy-AfTeR": header} if header is not None else {}
    api.responses.append(httpx.Response(429, headers=headers, content=b"not JSON"))
    async with bot:
        with pytest.raises(HTTPError) as captured:
            await bot.send_message(7, "private message", random_id=11)

    assert captured.value.status_code == 429
    assert captured.value.retry_after == expected
    if expected is not None:
        assert isinstance(captured.value.retry_after, float)
    assert len(api.requests) == 1


@pytest.mark.parametrize("path", ["api", "upload", "poll"])
async def test_shared_transport_exposes_delay_without_retry_or_sleep(
    bot: Bot, api: MockAPI, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    sleep = AsyncMock(side_effect=AssertionError("Transport must not wait"))
    monkeypatch.setattr("asyncio.sleep", sleep)
    api.responses.append(
        httpx.Response(
            503,
            headers={"Retry-After": "42", "X-Private": "private-header"},
            content=b"private-response",
        )
    )
    async with bot:
        if path == "api":
            operation = bot.send_message(7, "private-message", random_id=11)
        elif path == "upload":
            operation = bot.transport.upload(
                "https://upload.example/file", b"private-file", field="file"
            )
        else:
            operation = bot.transport.poll(
                "https://poll.example/events", key=SecretStr("private-key"), ts="1", wait=25
            )
        with pytest.raises(HTTPError) as captured:
            await operation

    error = captured.value
    assert error.status_code == 503
    assert error.retry_after == 42.0
    assert vars(error) == {"status_code": 503, "retry_after": 42.0}
    assert error.args == ("VK HTTP request failed with status 503",)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert len(api.requests) == 1
    sleep.assert_not_awaited()


async def test_vk_error_six_is_not_an_http_rate_limit(bot: Bot, api: MockAPI) -> None:
    api.responses.append(
        httpx.Response(
            200,
            headers={"Retry-After": "42"},
            json={"error": {"error_code": 6, "error_msg": "Too many requests"}},
        )
    )
    async with bot:
        with pytest.raises(RateLimitError) as captured:
            await bot.send_message(7, "message", random_id=11)
    assert captured.value.code == 6
    assert not isinstance(captured.value, HTTPError)
    assert not hasattr(captured.value, "retry_after")
    assert len(api.requests) == 1


def test_http_error_constructor_remains_compatible() -> None:
    error = HTTPError(429)
    assert error.status_code == 429
    assert error.retry_after is None
    assert str(error) == "VK HTTP request failed with status 429"
    assert HTTPError(429, retry_after=0.5).retry_after == 0.5


@pytest.mark.parametrize(
    ("header", "deadline"),
    [
        ("Wednesday, 06-Nov-75 12:00:00 GMT", datetime(2075, 11, 6, 12, tzinfo=timezone.utc)),
        ("Friday, 06-Nov-77 12:00:00 GMT", datetime(1977, 11, 6, 12, tzinfo=timezone.utc)),
    ],
)
async def test_obsolete_date_year_uses_fifty_year_rule(
    bot: Bot, api: MockAPI, header: str, deadline: datetime
) -> None:
    api.responses.append(httpx.Response(503, headers={"Retry-After": header}))
    async with bot:
        with pytest.raises(HTTPError) as captured:
            await bot.send_message(7, "message", random_id=11)
    expected = max(0.0, (deadline - datetime(2026, 11, 6, 12, tzinfo=timezone.utc)).total_seconds())
    assert captured.value.retry_after == expected
