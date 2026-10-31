"""Run with VK_TOKEN and VK_GROUP_ID set in the environment."""

import asyncio

from python_vk_bot import Application, Bot, BotSettings, Context, MessageHandler, Update, filters


async def echo(update: Update, context: Context) -> None:
    message = update.message
    if message is not None:
        await context.bot.send_message(message.peer_id, message.text)


async def main() -> None:
    settings = BotSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    application.add_handler(MessageHandler(echo, predicate=filters.TEXT))
    await application.run_polling(wait=settings.polling_wait)


if __name__ == "__main__":
    asyncio.run(main())
