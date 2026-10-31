"""Synthetic events and HTTP responses; never use live credentials."""

from collections import deque
from urllib.parse import parse_qs

import httpx
from pydantic import JsonValue


class MockAPI:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: deque[httpx.Response | Exception] = deque()

    def add(self, payload: JsonValue, *, status: int = 200) -> None:
        self.responses.append(httpx.Response(status, json=payload))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def form(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def event(
    event_id: str = "event-1",
    *,
    user_id: int = 7,
    peer_id: int = 2_000_000_001,
    text: str = "hello",
) -> dict[str, JsonValue]:
    return {
        "type": "message_new",
        "group_id": 42,
        "event_id": event_id,
        "v": "5.199",
        "object": {"message": message(user_id=user_id, peer_id=peer_id, text=text)},
    }


def message(
    *, user_id: int = 7, peer_id: int = 2_000_000_001, text: str = "hello"
) -> dict[str, JsonValue]:
    return {
        "id": 100,
        "from_id": user_id,
        "peer_id": peer_id,
        "conversation_message_id": 12,
        "text": text,
    }


def connection(ts: str = "10", key: str = "synthetic-poll-key") -> dict[str, JsonValue]:
    return {"response": {"server": "https://poll.example/events", "key": key, "ts": ts}}
