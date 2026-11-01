import json
from typing import Union
from urllib.parse import parse_qs

import pytest
from pydantic import JsonValue

from python_vk_bot import Attachment, Bot, Keyboard, PhotoAttachment
from python_vk_bot.errors import APIError, InvalidResponseError, RateLimitError

from .helpers import MockAPI, form, queue_photo_upload


def saved_photo() -> PhotoAttachment:
    return PhotoAttachment.model_validate(
        {"photo": {"id": 11, "owner_id": -42, "access_key": "key"}}
    )


@pytest.mark.parametrize("operation", ["send", "edit"])
async def test_send_and_edit_accept_typed_attachments(
    bot: Bot, api: MockAPI, operation: str
) -> None:
    api.add({"response": 1})
    keyboard = Keyboard(inline=True, buttons=[[{"action": {"type": "callback", "label": "Next"}}]])
    async with bot:
        if operation == "send":
            result = await bot.send_message(7, "Map", attachment=saved_photo(), keyboard=keyboard)
        else:
            result = await bot.edit_message(
                7, "Map", conversation_message_id=12, attachment=saved_photo(), keyboard=keyboard
            )
    assert result == 1
    data = form(api.requests[0])
    assert data["attachment"] == "photo-42_11_key"
    assert data["message"] == "Map"
    assert json.loads(data["keyboard"]) == keyboard.model_dump()
    if operation == "edit":
        assert data["cmid"] == "12"
        assert "message_id" not in data


@pytest.mark.parametrize("ready", ["string", "model"])
async def test_saved_media_bypasses_upload(bot: Bot, api: MockAPI, ready: str) -> None:
    api.add({"response": 1})
    photo = saved_photo()
    async with bot:
        assert await bot.edit_message_media(
            7,
            photo.to_attachment() if ready == "string" else photo,
            message_id=100,
            caption="Reused",
        )
    assert len(api.requests) == 1
    assert api.requests[0].url.path == "/method/messages.edit"
    assert form(api.requests[0])["attachment"] == "photo-42_11_key"


@pytest.mark.parametrize("cmid", [False, True])
async def test_media_upload_then_edit_preserves_explicit_keyboard_and_caption(
    bot: Bot, api: MockAPI, cmid: bool
) -> None:
    queue_photo_upload(api)
    api.add({"response": 1})
    keyboard = Keyboard(buttons=[], inline=True)
    async with bot:
        result = await bot.edit_message_media(
            7,
            b"new-image",
            caption="New map",
            keyboard=keyboard,
            filename="map.png",
            message_id=None if cmid else 100,
            conversation_message_id=12 if cmid else None,
        )
    assert result is True
    assert len(api.requests) == 4
    assert api.requests[-1].url.path == "/method/messages.edit"
    data = form(api.requests[-1])
    assert data["attachment"] == "photo-42_11_photo-key"
    assert data["message"] == "New map"
    assert data["cmid" if cmid else "message_id"] == ("12" if cmid else "100")
    assert json.loads(data["keyboard"]) == {"buttons": [], "inline": True, "one_time": False}


async def test_edit_omission_and_explicit_empty_fields(bot: Bot, api: MockAPI) -> None:
    api.add({"response": 1})
    api.add({"response": 1})
    api.add({"response": 1})
    async with bot:
        await bot.edit_message_media(7, "photo7_1", message_id=100)
        await bot.edit_message(7, "", message_id=100, attachment="")
        await bot.edit_message(7, "text-only", message_id=100)
    omitted = form(api.requests[0])
    assert "message" not in omitted
    assert "keyboard" not in omitted
    explicit = parse_qs(api.requests[1].content.decode(), keep_blank_values=True)
    assert explicit["message"] == [""]
    assert explicit["attachment"] == [""]
    assert "attachment" not in form(api.requests[2])


@pytest.mark.parametrize("code", [6, 909, 920, 949])
async def test_failed_media_edit_does_not_send_or_retry(bot: Bot, api: MockAPI, code: int) -> None:
    queue_photo_upload(api)
    api.add({"error": {"error_code": code, "error_msg": "private-details"}})
    async with bot:
        with pytest.raises(RateLimitError if code == 6 else APIError) as caught:
            await bot.edit_message_media(7, b"image", message_id=100)
    assert caught.value.method == "messages.edit"
    assert caught.value.code == code
    assert "private" not in str(caught.value)
    assert len(api.requests) == 4
    assert all(request.url.path != "/method/messages.send" for request in api.requests)


async def test_media_edit_returns_false_without_fallback(bot: Bot, api: MockAPI) -> None:
    api.add({"response": 0})
    async with bot:
        assert await bot.edit_message_media(7, "photo7_1", message_id=100) is False
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    ("message_id", "cmid"), [(None, None), (1, 1), (0, None), (-1, None), (None, True)]
)
async def test_invalid_media_identifiers_never_upload(
    bot: Bot, api: MockAPI, message_id: Union[int, None], cmid: Union[int, None]
) -> None:
    async with bot:
        with pytest.raises(ValueError, match="identifier"):
            await bot.edit_message_media(
                7, b"image", message_id=message_id, conversation_message_id=cmid
            )
    assert not api.requests


@pytest.mark.parametrize(
    "media", ["map.png", "https://example.com/photo.png", "doc7_1", "photo7_1,photo7_2"]
)
async def test_media_strings_are_single_photo_identifiers(
    bot: Bot, api: MockAPI, media: str
) -> None:
    async with bot:
        with pytest.raises(ValueError, match="photo identifier"):
            await bot.edit_message_media(7, media, message_id=100)
    assert not api.requests


async def test_unknown_attachment_is_not_sent(bot: Bot, api: MockAPI) -> None:
    unknown = Attachment.model_validate({"type": "unknown", "unknown": {"id": 1}})
    async with bot:
        with pytest.raises(ValueError, match="supported, complete"):
            await bot.send_message(7, attachment=unknown)
        with pytest.raises(ValueError, match="text or an attachment"):
            await bot.edit_message(7, message_id=100)
    assert not api.requests


@pytest.mark.parametrize("cmid", [False, True])
@pytest.mark.parametrize("success", [0, 1])
async def test_delete_identifiers_scope_and_status(
    bot: Bot, api: MockAPI, cmid: bool, success: int
) -> None:
    api.add(
        {
            "response": [
                {
                    "peer_id": 7,
                    "message_id": 100,
                    "conversation_message_id": 12,
                    "response": success,
                }
            ]
        }
    )
    async with bot:
        result = await bot.delete_message(
            7,
            message_id=None if cmid else 100,
            conversation_message_id=12 if cmid else None,
            delete_for_all=cmid,
            spam=cmid,
        )
    assert result is (success == 1)
    data = form(api.requests[0])
    assert data == {
        "v": "5.199",
        "peer_id": "7",
        "cmids" if cmid else "message_ids": "12" if cmid else "100",
        "delete_for_all": "1" if cmid else "0",
        "spam": "1" if cmid else "0",
    }


@pytest.mark.parametrize("status", [0, 1])
async def test_delete_global_id_mapping(bot: Bot, api: MockAPI, status: int) -> None:
    api.add({"response": {"100": status}})
    async with bot:
        assert await bot.delete_message(7, message_id=100) is (status == 1)


@pytest.mark.parametrize("code", [6, 924])
async def test_delete_per_message_error(bot: Bot, api: MockAPI, code: int) -> None:
    api.add(
        {
            "response": [
                {
                    "peer_id": 7,
                    "conversation_message_id": 12,
                    "error": {"code": code, "description": "private-error"},
                }
            ]
        }
    )
    async with bot:
        with pytest.raises(RateLimitError if code == 6 else APIError) as caught:
            await bot.delete_message(7, conversation_message_id=12, delete_for_all=True)
    assert caught.value.method == "messages.delete"
    assert caught.value.code == code
    assert "private" not in str(caught.value)
    assert len(api.requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        1,
        [],
        [{}, {}],
        {"12": 1},
        [{"peer_id": 7, "conversation_message_id": 99, "response": 1}],
        [{"peer_id": 8, "conversation_message_id": 12, "response": 1}],
        [{"peer_id": 7, "conversation_message_id": 12}],
        [{"peer_id": 7, "conversation_message_id": 12, "response": True}],
        [{"peer_id": 7, "conversation_message_id": 12, "response": 2}],
    ],
)
async def test_delete_rejects_ambiguous_or_malformed_results(
    bot: Bot, api: MockAPI, payload: JsonValue
) -> None:
    api.add({"response": payload})
    async with bot:
        with pytest.raises(InvalidResponseError):
            await bot.delete_message(7, conversation_message_id=12)
    assert len(api.requests) == 1
