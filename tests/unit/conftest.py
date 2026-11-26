import os
import socket
from collections.abc import AsyncIterator
from typing import Never

import httpx2
import pytest

from python_vk_bot import Application, Bot

from .helpers import MockAPI


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("VK_"):
            monkeypatch.delenv(name)

    def no_network(*args: object, **kwargs: object) -> Never:
        raise AssertionError("Unit tests must not access live networks")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)


@pytest.fixture
def api() -> MockAPI:
    return MockAPI()


@pytest.fixture
async def client(api: MockAPI) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(api)) as client:
        yield client


@pytest.fixture
def bot(client: httpx2.AsyncClient) -> Bot:
    return Bot("synthetic-community-token", client=client)


@pytest.fixture
def application(bot: Bot) -> Application:
    return Application(bot, group_id=42)
