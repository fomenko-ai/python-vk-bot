"""Typed handler registration without a conversation-state framework."""

from collections.abc import Awaitable, Callable

from . import filters
from .context import Context
from .models import Update

type HandlerCallback = Callable[[Update, Context], Awaitable[None]]


class Handler:
    def __init__(
        self, callback: HandlerCallback, *, predicate: filters.Filter = filters.ALL
    ) -> None:
        self.callback = callback
        self.predicate = predicate

    def check_update(self, update: Update) -> bool:
        return self.predicate(update)

    async def handle_update(self, update: Update, context: Context) -> None:
        await self.callback(update, context)


class MessageHandler(Handler):
    def __init__(
        self, callback: HandlerCallback, *, predicate: filters.Filter = filters.ALL
    ) -> None:
        super().__init__(
            callback,
            predicate=filters.Filter(lambda update: update.message is not None) & predicate,
        )


class MessageEventHandler(Handler):
    def __init__(
        self, callback: HandlerCallback, *, predicate: filters.Filter = filters.ALL
    ) -> None:
        super().__init__(
            callback,
            predicate=filters.Filter(lambda update: update.message_event is not None) & predicate,
        )


class CommandHandler(MessageHandler):
    """Match an explicit /command token; no Telegram mention syntax is inferred."""

    def __init__(self, command: str, callback: HandlerCallback) -> None:
        if not command or command.startswith("/") or any(char.isspace() for char in command):
            raise ValueError("command must be a nonempty token without a leading slash")
        super().__init__(
            callback,
            predicate=filters.Filter(
                lambda update: (
                    update.message is not None
                    and update.message.text.split(maxsplit=1)[:1] == [f"/{command}"]
                )
            ),
        )
