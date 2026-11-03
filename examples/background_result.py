"""A local background calculation; only message delivery uses VK."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from python_vk_bot import (
    Application,
    ApplicationHandlerStop,
    Bot,
    BotSettings,
    CommandHandler,
    Context,
    TypeHandler,
    Update,
)


@dataclass(frozen=True)
class BackgroundResult:
    peer_id: int
    text: str


async def calculate(
    application: Application, peer_id: int, user_id: Optional[int], text: str
) -> None:
    # A local asynchronous stand-in for a bounded computation, without AI or brokers.
    await asyncio.sleep(0.1)
    result = BackgroundResult(peer_id, f"Result: {len(text)} characters.")
    await application.update_queue.put(result, user_id=user_id, peer_id=peer_id)


async def start_calculation(update: Update, context: Context) -> None:
    message = update.message
    if message is None:
        return
    text = message.text.partition(" ")[2]
    await context.bot.send_message(message.peer_id, "Calculation started.")
    context.application.create_task(
        calculate(context.application, message.peer_id, update.user_id, text),
        update=update,
        name="background-calculation",
    )
    raise ApplicationHandlerStop


async def handle_result(result: BackgroundResult, context: Context) -> None:
    await context.bot.send_message(result.peer_id, result.text)
    context.peer_data["last_result"] = result.text


def configure(application: Application) -> None:
    application.add_handler(CommandHandler("background", start_calculation), group=-1)
    application.add_handler(TypeHandler(BackgroundResult, handle_result))


async def main() -> None:
    settings = BotSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    configure(application)
    await application.run_polling(wait=settings.polling_wait)


if __name__ == "__main__":
    asyncio.run(main())
