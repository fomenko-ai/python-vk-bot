"""HTTPX2 dependency boundaries and transport security, without live requests."""

import logging
import traceback

import httpx2
import pytest
from pydantic import SecretStr

from python_vk_bot import Bot
from python_vk_bot.errors import HTTPError, InvalidResponseError, LifecycleError, NetworkError

from .helpers import MockAPI


def test_foreign_client_rejected_without_retaining_its_details() -> None:
    class ForeignClient:
        def __repr__(self) -> str:
            return "private-client-credentials"

    with pytest.raises(TypeError, match=r"httpx2\.AsyncClient") as caught:
        Bot(
            "synthetic-token",
            client=ForeignClient(),  # ty: ignore[invalid-argument-type] -- foreign dependency boundary
        )
    assert "private" not in str(caught.value)


async def test_owned_client_recreated_after_shutdown(
    api: MockAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_type = httpx2.AsyncClient
    created: list[httpx2.AsyncClient] = []

    def factory(**kwargs: object) -> httpx2.AsyncClient:
        client = client_type(transport=httpx2.MockTransport(api))
        created.append(client)
        return client

    monkeypatch.setattr("python_vk_bot.transport.httpx2.AsyncClient", factory)
    bot = Bot("synthetic-token")
    api.add({"response": 1})
    api.add({"response": 2})
    try:
        await bot.initialize()
        await bot.initialize()
        assert len(created) == 1
        assert await bot.request("users.get", {}) == 1
        await bot.shutdown()
        await bot.shutdown()
        assert created[0].is_closed
        with pytest.raises(LifecycleError):
            await bot.request("users.get", {})
        await bot.initialize()
        assert len(created) == 2
        assert not created[1].is_closed
        assert await bot.request("users.get", {}) == 2
    finally:
        await bot.shutdown()
    assert all(client.is_closed for client in created)


async def test_borrowed_client_reused_across_bot_contexts(
    client: httpx2.AsyncClient, api: MockAPI
) -> None:
    bot = Bot("synthetic-token", client=client)
    for result in (1, 2):
        api.add({"response": result})
        async with bot:
            assert await bot.request("users.get", {}) == result
        assert not client.is_closed
    await client.aclose()
    with pytest.raises(LifecycleError, match="closed"):
        await bot.initialize()


@pytest.mark.parametrize(
    "error_type",
    [
        httpx2.ConnectTimeout,
        httpx2.ReadTimeout,
        httpx2.WriteTimeout,
        httpx2.PoolTimeout,
        httpx2.ConnectError,
        httpx2.ReadError,
        httpx2.WriteError,
        httpx2.RemoteProtocolError,
    ],
)
async def test_poll_network_errors_hide_url_and_key_in_tracebacks(
    bot: Bot, api: MockAPI, error_type: type[httpx2.RequestError]
) -> None:
    server = "https://poll.example/"
    poll_key = SecretStr("private-key")
    api.responses.append(error_type("https://poll.example/?key=private-key private-token"))
    async with bot:
        with pytest.raises(NetworkError) as caught:
            await bot.transport.poll(server, key=poll_key, ts="1", wait=25)
    formatted = "".join(traceback.format_exception(caught.value))
    assert "private-key" not in formatted
    assert "private-token" not in formatted
    assert "https://poll.example" not in formatted
    assert len(api.requests) == 1


@pytest.mark.parametrize("operation", ["poll", "upload"])
@pytest.mark.parametrize(
    "server",
    [
        "https://[private-key",
        "https://poll.example:private-key/",
        "https://private-key:password@poll.example/",
        "https://poll.example/#private-key",
        "https://poll.example/\nprivate-key",
    ],
)
async def test_invalid_server_urls_do_not_leak_or_send(
    bot: Bot, api: MockAPI, operation: str, server: str
) -> None:
    poll_key = SecretStr("private-key")
    async with bot:
        request = (
            bot.transport.poll(server, key=poll_key, ts="1", wait=25)
            if operation == "poll"
            else bot.transport.upload(server, b"image", field="photo")
        )
        with pytest.raises(InvalidResponseError) as caught:
            await request
    assert "private-key" not in "".join(traceback.format_exception(caught.value))
    assert not api.requests


@pytest.mark.parametrize("operation", ["api", "poll", "upload"])
@pytest.mark.parametrize("location", ["https://redirect.example/?key=private-key", "http://["])
async def test_injected_redirect_policy_cannot_forward_credentials(
    api: MockAPI, caplog: pytest.LogCaptureFixture, operation: str, location: str
) -> None:
    api.responses.append(httpx2.Response(302, headers={"location": location}))
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(api), follow_redirects=True
    ) as client:
        bot = Bot("private-token", client=client)
        server = "https://poll.example/"
        poll_key = SecretStr("private-key")
        with caplog.at_level(logging.DEBUG):
            async with bot:
                if operation == "api":
                    request = bot.send_message(7, "private-message", random_id=1)
                elif operation == "poll":
                    request = bot.transport.poll(server, key=poll_key, ts="1", wait=25)
                else:
                    request = bot.transport.upload(
                        "https://upload.example/?hash=private-key", b"private-file", field="photo"
                    )
                with pytest.raises(HTTPError) as caught:
                    await request
        assert not client.is_closed
    assert caught.value.status_code == 302
    assert len(api.requests) == 1
    assert "HTTP Request" in caplog.text
    assert not any(
        secret in caplog.text + str(caught.value)
        for secret in ("private-key", "private-token", "private-message", "private-file")
    )


async def test_request_timeouts_override_injected_client_default(api: MockAPI) -> None:
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(api), timeout=None) as client:
        async with Bot("synthetic-token", client=client, timeout=40) as bot:
            api.add({"response": 1})
            await bot.request("users.get", {})
            api.add({"ts": "2", "updates": []})
            await bot.transport.poll(
                "https://poll.example/", key=SecretStr("synthetic-key"), ts="1", wait=90
            )
            api.add({})
            await bot.transport.upload("https://upload.example/", b"image", field="photo")
        assert client.timeout == httpx2.Timeout(None)
    assert [request.extensions["timeout"] for request in api.requests] == [
        dict.fromkeys(("connect", "read", "write", "pool"), timeout) for timeout in (40, 100, 40)
    ]
