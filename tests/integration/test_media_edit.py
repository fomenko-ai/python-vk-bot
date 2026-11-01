"""Opt-in test that creates, edits, reads and deletes its own VK test message.

Requires VK_RUN_MEDIA_INTEGRATION=1, VK_TEST_TOKEN and VK_TEST_PEER_ID.
Never run against a conversation where synthetic test messages are unwanted.
"""

import asyncio
import os
import secrets

import pytest

from examples.interactive_map import render_map
from python_vk_bot import Bot, Keyboard, Message, PhotoAttachment
from python_vk_bot.models.messages import MessagePage

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("VK_RUN_MEDIA_INTEGRATION") != "1",
        reason="Live media test disabled; opt in with VK_RUN_MEDIA_INTEGRATION=1",
    ),
]


def keyboard(label: str) -> Keyboard:
    return Keyboard(
        inline=True,
        buttons=[
            [
                {
                    "action": {"type": "callback", "label": label, "payload": '{"test":"media"}'},
                    "color": "secondary",
                }
            ]
        ],
    )


def photo_identity(message: Message) -> tuple[int, int]:
    photos = [item for item in message.typed_attachments if isinstance(item, PhotoAttachment)]
    assert len(photos) == 1
    return photos[0].photo.owner_id, photos[0].photo.id


def keyboard_label(message: Message) -> str:
    raw = (message.model_extra or {}).get("keyboard")
    assert isinstance(raw, dict)
    parsed = Keyboard.model_validate(raw)
    assert parsed.inline
    action = parsed.buttons[0][0]["action"]
    assert isinstance(action, dict)
    label = action["label"]
    assert isinstance(label, str)
    return label


@pytest.mark.parametrize("identifier", ["message_id", "conversation_message_id"])
async def test_replace_photo_in_same_message(identifier: str) -> None:
    token = os.environ.get("VK_TEST_TOKEN")
    raw_peer = os.environ.get("VK_TEST_PEER_ID")
    if not token or not raw_peer:
        pytest.skip("VK_TEST_TOKEN and VK_TEST_PEER_ID are required")
    peer_id = int(raw_peer)
    if peer_id == 0:
        pytest.fail("VK_TEST_PEER_ID must be nonzero")
    suffix = secrets.token_hex(4)
    original_text = f"python-vk-bot integration before {suffix}"
    updated_text = f"python-vk-bot integration after {suffix}"
    message_id: int | None = None
    cmid: int | None = None
    async with Bot(token) as bot:
        try:
            initial = await bot.upload_photo(
                peer_id, await asyncio.to_thread(render_map, 0, 0, 1), filename="before.png"
            )
            message_id = await bot.send_message(
                peer_id, original_text, attachment=initial, keyboard=keyboard("Before")
            )
            assert message_id > 0, "Expected a global ID to retrieve the newly created message"
            # getById is used only to discover the cmid of this newly created message.
            page = MessagePage.model_validate(
                await bot.request(
                    "messages.getById", {"message_ids": message_id, "peer_id": peer_id}
                )
            )
            assert len(page.items) == 1
            before = page.items[0]
            assert before.peer_id == peer_id
            assert before.id == message_id
            cmid = before.conversation_message_id
            assert cmid > 0
            assert before.text == original_text
            assert photo_identity(before) == (initial.photo.owner_id, initial.photo.id)
            assert keyboard_label(before) == "Before"
            assert await bot.edit_message_media(
                peer_id,
                await asyncio.to_thread(render_map, 1, 1, 2),
                message_id=message_id if identifier == "message_id" else None,
                conversation_message_id=cmid if identifier == "conversation_message_id" else None,
                caption=updated_text,
                keyboard=keyboard("After"),
                filename="after.png",
            )
            after = await bot.get_message(peer_id, cmid)
            assert after is not None
            assert after.peer_id == before.peer_id
            assert after.id == before.id
            assert after.conversation_message_id == before.conversation_message_id
            assert photo_identity(after) != photo_identity(before)
            assert after.text == updated_text
            assert keyboard_label(after) == "After"
        finally:
            # Delete only the message this test created. Failure is visible; no history
            # scan or broad deletion is used if creation returned no usable identifier.
            if cmid is not None or (message_id is not None and message_id > 0):
                deleted = await bot.delete_message(
                    peer_id,
                    message_id=message_id if cmid is None else None,
                    conversation_message_id=cmid,
                    delete_for_all=True,
                )
                assert deleted, "VK did not confirm cleanup of the test message"
