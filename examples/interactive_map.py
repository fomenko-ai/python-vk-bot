"""Run with VK_TOKEN and VK_GROUP_ID; enable message_new and message_event.

Send /map to the community. One active map is kept per peer in this process.
The generated PNG is a synthetic grid, not geographical data. Live photo replacement
must still be verified with the target community; VK editing errors propagate.
"""

import asyncio
import json
import secrets
import struct
import zlib
from dataclasses import dataclass, field

from python_vk_bot import (
    Application,
    Bot,
    BotSettings,
    CommandHandler,
    Context,
    Keyboard,
    MessageEventHandler,
    Update,
)
from python_vk_bot.errors import VKError


@dataclass
class MapState:
    owner_id: int
    message_id: int
    session: str
    x: int = 0
    y: int = 0
    zoom: int = 1
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def render_map(x: int, y: int, zoom: int) -> bytes:
    """Small PNG generator using only the standard library; replace with your renderer."""
    size = 256
    pixels = bytearray()
    for row in range(size):
        pixels.append(0)  # PNG scanline filter: none.
        for column in range(size):
            world_x = (column - size // 2) // zoom + x * 16
            world_y = (row - size // 2) // zoom + y * 16
            if world_x % 32 == 0 or world_y % 32 == 0:
                pixels.extend((40, 55, 65))
            else:
                pixels.extend((80 + world_x % 120, 90 + world_y % 120, 140))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(pixels)))
        + _png_chunk(b"IEND", b"")
    )


def map_keyboard(session: str) -> Keyboard:
    return Keyboard(
        inline=True,
        buttons=[
            [
                {
                    "action": {
                        "type": "callback",
                        "label": label,
                        "payload": json.dumps({"map": session, "move": move}),
                    },
                    "color": "secondary",
                }
                for label, move in row
            ]
            for row in [
                [("←", "left"), ("↑", "up"), ("↓", "down"), ("→", "right")],
                [("+", "in"), ("−", "out")],  # noqa: RUF001 -- mathematical minus button
            ]
        ],
    )


def caption(x: int, y: int, zoom: int) -> str:
    return f"Тестовая карта: x={x}, y={y}, масштаб={zoom}"


async def show_map(update: Update, context: Context) -> None:
    message = update.message
    if message is None:
        return
    session = secrets.token_hex(8)
    image = await asyncio.to_thread(render_map, 0, 0, 1)
    photo = await context.bot.upload_photo(message.peer_id, image, filename="map.png")
    message_id = await context.bot.send_message(
        message.peer_id,
        caption(0, 0, 1),
        attachment=photo,
        keyboard=map_keyboard(session),
    )
    context.peer_data["interactive_map"] = MapState(message.from_id, message_id, session)


async def navigate(update: Update, context: Context) -> None:
    event = update.message_event
    if event is None:
        return
    payload = event.payload
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return
    if not isinstance(payload, dict) or "map" not in payload:
        return
    state = context.peer_data.get("interactive_map")
    if (
        not isinstance(state, MapState)
        or payload.get("map") != state.session
        or event.user_id != state.owner_id
    ):
        await context.bot.send_message_event_answer(
            event.event_id,
            event.user_id,
            event.peer_id,
            {"type": "show_snackbar", "text": "Отправьте /map, чтобы открыть свою карту"},
        )
        return
    move = payload.get("move")
    if not isinstance(move, str) or move not in {"left", "right", "up", "down", "in", "out"}:
        return
    await context.bot.send_message_event_answer(
        event.event_id,
        event.user_id,
        event.peer_id,
        {"type": "show_snackbar", "text": "Обновляю карту"},
    )
    # Serialize the complete read-render-upload-edit cycle for this message. No
    # background renderer can finish late and overwrite a more recent edit.
    async with state.lock:
        x = state.x + (move == "right") - (move == "left")
        y = state.y + (move == "down") - (move == "up")
        zoom = max(1, min(8, state.zoom + (move == "in") - (move == "out")))
        image = await asyncio.to_thread(render_map, x, y, zoom)
        edited = await context.bot.edit_message_media(
            event.peer_id,
            image,
            message_id=state.message_id if event.conversation_message_id is None else None,
            conversation_message_id=event.conversation_message_id,
            caption=caption(x, y, zoom),
            keyboard=map_keyboard(state.session),
            filename="map.png",
        )
        if not edited:
            raise VKError("VK did not confirm the map edit")
        state.x, state.y, state.zoom = x, y, zoom


async def main() -> None:
    settings = BotSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    application.add_handler(CommandHandler("map", show_map))
    application.add_handler(MessageEventHandler(navigate))
    await application.run_polling(wait=settings.polling_wait)


if __name__ == "__main__":
    asyncio.run(main())
