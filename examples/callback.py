"""ASGI factory: uvicorn examples.callback:create_app --factory."""

from pydantic import Field, SecretStr
from starlette.applications import Starlette

from python_vk_bot import (
    Application,
    Bot,
    BotSettings,
    Callback,
    Context,
    MessageHandler,
    Update,
    filters,
)


class CallbackSettings(BotSettings):
    """Add VK_CALLBACK_SECRET and VK_CALLBACK_CONFIRMATION for this example."""

    callback_secret: SecretStr = Field(min_length=1, repr=False)
    callback_confirmation: SecretStr = Field(min_length=1, repr=False)


async def echo(update: Update, context: Context) -> None:
    message = update.message
    if message is not None:
        await context.bot.send_message(message.peer_id, message.text)


def create_app() -> Starlette:
    settings = CallbackSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    application.add_handler(MessageHandler(echo, predicate=filters.TEXT))
    callback = Callback(
        application,
        secret=settings.callback_secret,
        confirmation_code=settings.callback_confirmation,
    )
    return callback.create_app()
