import asyncio
import json
import struct
import zlib

import httpx
import pytest
from async_timeout import timeout
from pydantic import JsonValue

from examples.interactive_map import MapState, navigate, render_map, show_map
from python_vk_bot import Application, Bot, Context, Update
from python_vk_bot.errors import APIError, VKError

from .helpers import MockAPI, event, form, queue_photo_upload, running_task


def button_event(
    move: str = "right", *, event_id: str = "first", user_id: int = 7, session: str = "map-session"
) -> Update:
    return Update.from_dict(
        {
            "type": "message_event",
            "group_id": 42,
            "v": "5.199",
            "event_id": event_id,
            "object": {
                "event_id": event_id,
                "user_id": user_id,
                "peer_id": 7,
                "conversation_message_id": 12,
                "payload": json.dumps({"map": session, "move": move}),
            },
        }
    )


def map_context(bot: Bot, state: MapState) -> Context:
    return Context(
        application=Application(bot, group_id=42),
        bot=bot,
        user_data={},
        bot_data={},
        peer_data={"interactive_map": state},
    )


def test_renderer_produces_valid_changing_png() -> None:
    png = render_map(0, 0, 1)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    chunks: dict[bytes, bytes] = {}
    while offset < len(png):
        length = struct.unpack_from(">I", png, offset)[0]
        kind = png[offset + 4 : offset + 8]
        data = png[offset + 8 : offset + 8 + length]
        checksum = struct.unpack_from(">I", png, offset + 8 + length)[0]
        assert checksum == zlib.crc32(kind + data)
        chunks[kind] = chunks.get(kind, b"") + data
        offset += 12 + length
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[b"IHDR"]
    )
    assert (depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0)
    pixels = zlib.decompress(chunks[b"IDAT"])
    assert len(pixels) == height * (1 + width * 3)
    assert pixels[:: 1 + width * 3] == b"\0" * height
    assert chunks[b"IEND"] == b""
    assert png != render_map(1, 0, 1)
    assert png != render_map(0, 0, 2)


async def test_initial_map_is_uploaded_and_sent(bot: Bot, api: MockAPI) -> None:
    queue_photo_upload(api)
    api.add({"response": 100})
    context = map_context(bot, MapState(7, 1, "old-session"))
    async with bot:
        await show_map(Update.from_dict(event(user_id=7, peer_id=7, text="/map")), context)
    state = context.peer_data["interactive_map"]
    assert isinstance(state, MapState)
    assert state.message_id == 100
    assert state.owner_id == 7
    assert state.session != "old-session"
    data = form(api.requests[-1])
    assert api.requests[-1].url.path == "/method/messages.send"
    assert data["attachment"] == "photo-42_11_photo-key"
    keyboard = json.loads(data["keyboard"])
    assert keyboard["inline"] is True
    assert len(keyboard["buttons"]) == 2
    assert json.loads(keyboard["buttons"][0][0]["action"]["payload"])["map"] == state.session


async def test_concurrent_navigation_serializes_render_upload_and_edit() -> None:
    first_upload = asyncio.Event()
    release_upload = asyncio.Event()
    second_ack = asyncio.Event()
    uploads = 0
    saved = 0
    edits: list[dict[str, str]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal uploads, saved
        path = request.url.path
        if path == "/method/messages.sendMessageEventAnswer":
            if form(request)["event_id"] == "second":
                second_ack.set()
            payload: JsonValue = {"response": 1}
        elif path == "/method/photos.getMessagesUploadServer":
            payload = {"response": {"upload_url": "https://upload.example/photo"}}
        elif request.url.host == "upload.example":
            uploads += 1
            if uploads == 1:
                first_upload.set()
                await release_upload.wait()
            payload = {"server": 1, "photo": "opaque", "hash": "hash"}
        elif path == "/method/photos.saveMessagesPhoto":
            saved += 1
            payload = {"response": [{"owner_id": -42, "id": saved}]}
        elif path == "/method/messages.edit":
            edits.append(form(request))
            payload = {"response": 1}
        else:
            raise AssertionError("Unexpected request, including fallback sends")
        return httpx.Response(200, json=payload)

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client,
        Bot("synthetic", client=client) as bot,
        timeout(3),
    ):
        state = MapState(7, 100, "map-session")
        context = map_context(bot, state)
        async with running_task(navigate(button_event(), context)) as first:
            await first_upload.wait()
            async with running_task(navigate(button_event(event_id="second"), context)) as second:
                try:
                    await second_ack.wait()
                    assert uploads == 1
                    assert not edits
                    assert state.x == 0
                finally:
                    release_upload.set()
                await asyncio.gather(first, second)
        assert state.x == 2
        assert not state.lock.locked()
    assert [edit["message"] for edit in edits] == [
        "Тестовая карта: x=1, y=0, масштаб=1",
        "Тестовая карта: x=2, y=0, масштаб=1",
    ]
    assert [edit["attachment"] for edit in edits] == ["photo-42_1", "photo-42_2"]
    assert all(edit["cmid"] == "12" and "message_id" not in edit for edit in edits)
    assert edits[0]["keyboard"] == edits[1]["keyboard"]


@pytest.mark.parametrize("api_error", [False, True])
async def test_failed_navigation_keeps_state_and_releases_lock(
    bot: Bot, api: MockAPI, api_error: bool
) -> None:
    api.add({"response": 1})
    queue_photo_upload(api)
    api.add(
        {"error": {"error_code": 909, "error_msg": "expired"}} if api_error else {"response": 0}
    )
    state = MapState(7, 100, "map-session")
    context = map_context(bot, state)
    async with bot:
        with pytest.raises(APIError if api_error else VKError):
            await navigate(button_event(), context)
        assert state.x == 0
        assert not state.lock.locked()
        api.add({"response": 1})
        queue_photo_upload(api)
        api.add({"response": 1})
        await navigate(button_event(event_id="retry"), context)
    assert state.x == 1
    assert len(api.requests) == 10


@pytest.mark.parametrize(("user_id", "session"), [(8, "map-session"), (7, "expired")])
async def test_foreign_or_expired_buttons_do_not_change_map(
    bot: Bot, api: MockAPI, user_id: int, session: str
) -> None:
    api.add({"response": 1})
    state = MapState(7, 100, "map-session")
    async with bot:
        await navigate(button_event(user_id=user_id, session=session), map_context(bot, state))
    assert len(api.requests) == 1
    assert api.requests[0].url.path == "/method/messages.sendMessageEventAnswer"
    assert state.x == 0
