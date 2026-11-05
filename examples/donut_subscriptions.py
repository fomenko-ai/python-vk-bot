"""ASGI factory: uvicorn examples.donut_subscriptions:create_app --factory.

Remember event facts in memory; /donut in a private conversation shows the latest
received fact. This example does not synchronize subscriptions or grant access.
"""

from pydantic import Field, SecretStr
from starlette.applications import Starlette

from python_vk_bot import (
    Application,
    Bot,
    BotSettings,
    Callback,
    CommandHandler,
    Context,
    DonutSubscriptionHandler,
    Update,
)


class DonutSettings(BotSettings):
    """Read VK_CALLBACK_SECRET and VK_CALLBACK_CONFIRMATION with bot settings."""

    callback_secret: SecretStr = Field(min_length=1, repr=False)
    callback_confirmation: SecretStr = Field(min_length=1, repr=False)


async def on_donut(update: Update, context: Context) -> None:
    event = update.donut_subscription
    if event is None:
        return

    # Application selects user_data using event.user_id. There is no peer here.
    # This is only the latest received fact, not persistent subscription state.
    context.user_data["last_donut_event"] = update.type


async def show_last_event(update: Update, context: Context) -> None:
    message = update.message
    if message is None or message.peer_id != message.from_id:
        return  # Show a user's subscription information only in a private conversation.

    event_type = context.user_data.get("last_donut_event")
    if event_type == "donut_subscription_create":
        description = "Оформление подписки."
    elif event_type == "donut_subscription_prolonged":
        description = "Продление подписки."
    elif event_type == "donut_subscription_cancelled":
        description = "Отмена автопродления — это не означает истечение доступа."
    elif event_type == "donut_subscription_expired":
        description = "Истечение подписки."
    elif event_type == "donut_subscription_price_changed":
        description = "Изменение стоимости подписки."
    else:
        await context.bot.send_message(
            message.peer_id,
            "Бот ещё не получал события вашей подписки. Это не означает, что подписки нет.",
        )
        return

    await context.bot.send_message(
        message.peer_id,
        f"Последнее полученное событие: {description}\n"
        "История уведомлений не подтверждает текущий оплаченный доступ.",
    )


def create_app() -> Starlette:
    settings = DonutSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    application.add_handler(DonutSubscriptionHandler(on_donut))
    application.add_handler(CommandHandler("donut", show_last_event))
    callback = Callback(
        application,
        secret=settings.callback_secret,
        confirmation_code=settings.callback_confirmation,
    )
    return callback.create_app()
