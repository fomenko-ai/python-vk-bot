"""Run: uv run python examples/keyboards.py (see examples/README.md).

Set VK_TOKEN and VK_GROUP_ID; enable Bots Long Poll, message_new and message_event.
Send /keyboard for text/location buttons or /inline for callback/link buttons.
"""

import asyncio
import json

from pydantic import JsonValue

from python_vk_bot import (
    Application,
    Bot,
    BotSettings,
    ButtonColor,
    CallbackButton,
    CommandHandler,
    Context,
    Keyboard,
    LocationButton,
    MessageEventHandler,
    MessageHandler,
    OpenLinkButton,
    ShowSnackbar,
    TextButton,
    Update,
)
from python_vk_bot.errors import VKError


def regular_keyboard() -> Keyboard:
    keyboard = Keyboard(
        inline=False,
        one_time=False,
        buttons=[
            [
                TextButton(label=label, payload={"example": "keyboards", "action": action})
                for label, action in row
            ]
            for row in [
                [("Помощь", "help"), ("О боте", "about")],  # noqa: RUF001 -- Russian label
                [("Скрыть клавиатуру", "hide")],
            ]
        ],
    )
    keyboard.buttons.append([LocationButton()])
    return keyboard


def inline_keyboard() -> Keyboard:
    return Keyboard(
        inline=True,
        buttons=[
            [
                CallbackButton(
                    label="Подтвердить",
                    payload={"example": "keyboards", "action": "confirm"},
                    color=ButtonColor.POSITIVE,
                ),
                CallbackButton(
                    label="Отмена",
                    payload={"example": "keyboards", "action": "cancel"},
                    color=ButtonColor.NEGATIVE,
                ),
            ],
            [OpenLinkButton(label="Документация", link="https://dev.vk.com/ru/api/bots")],
        ],
    )


def parse_action(payload: JsonValue) -> str | None:
    """Message payload is a JSON string; event payload may already be an object."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return None
    if not isinstance(payload, dict) or payload.get("example") != "keyboards":
        return None
    action = payload.get("action")
    return action if isinstance(action, str) else None


async def show_keyboard(update: Update, context: Context) -> None:
    message = update.message
    if message is not None:
        await context.bot.send_message(
            message.peer_id, "Выберите действие:", keyboard=regular_keyboard()
        )


async def show_inline(update: Update, context: Context) -> None:
    message = update.message
    if message is not None:
        await context.bot.send_message(
            message.peer_id, "Подтвердить действие?", keyboard=inline_keyboard()
        )


async def handle_text_button(update: Update, context: Context) -> None:
    message = update.message
    if message is None:
        return
    action = parse_action(message.payload)
    replies = {
        "help": "Команды: /keyboard — обычная клавиатура, /inline — inline-клавиатура.",
        "about": "Это пример клавиатур python-vk-bot.",
        "hide": "Клавиатура скрыта. Отправьте /keyboard, чтобы вернуть её.",
    }
    if action is None or action not in replies:
        return
    await context.bot.send_message(
        message.peer_id,
        replies[action],
        keyboard=Keyboard(buttons=[]) if action == "hide" else regular_keyboard(),
    )


async def handle_inline_button(update: Update, context: Context) -> None:
    event = update.message_event
    if event is None:
        return
    action = parse_action(event.payload)
    if action not in {"confirm", "cancel"}:
        return
    text = "Подтверждено" if action == "confirm" else "Отменено"
    if event.conversation_message_id is None:
        text = "Отсутствует ID сообщения. Отправьте /inline ещё раз."
    await context.bot.send_message_event_answer(
        event.event_id,
        event.user_id,
        event.peer_id,
        ShowSnackbar(text=text),
    )
    if event.conversation_message_id is None:
        return
    # Keep the buttons so the demo can be tried repeatedly. In a conversation,
    # any participant can change this demonstration message's selection.
    edited = await context.bot.edit_message(
        event.peer_id,
        text,
        conversation_message_id=event.conversation_message_id,
        keyboard=inline_keyboard(),
    )
    if not edited:
        raise VKError("VK did not confirm the keyboard message edit")


async def main() -> None:
    settings = BotSettings()
    bot = Bot(settings.token, api_version=settings.api_version, timeout=settings.timeout)
    application = Application(bot, settings.group_id)
    # The first matching handler in each group runs; commands precede the catch-all.
    application.add_handler(CommandHandler("keyboard", show_keyboard))
    application.add_handler(CommandHandler("inline", show_inline))
    application.add_handler(MessageHandler(handle_text_button))
    application.add_handler(MessageEventHandler(handle_inline_button))
    await application.run_polling(wait=settings.polling_wait)


if __name__ == "__main__":
    asyncio.run(main())
