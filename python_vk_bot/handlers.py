"""Typed handler registration without a conversation-state framework."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Generic, Protocol, TypeVar

from typing_extensions import TypeAlias, TypeGuard

from . import filters
from .context import Context
from .models import Update

T = TypeVar("T")

HandlerCallback: TypeAlias = Callable[[Update, Context], Awaitable[None]]


class _DispatchHandler(Protocol):
    async def _dispatch(self, update: object, context: Context) -> bool: ...


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

    async def _dispatch(self, update: object, context: Context) -> bool:
        if not isinstance(update, Update) or not self.check_update(update):
            return False
        await self.handle_update(update, context)
        return True


class TypeHandler(Generic[T]):
    """Route a Python object by type, including validated VK Updates."""

    def __init__(
        self,
        update_type: type[T],
        callback: Callable[[T, Context], Awaitable[None]],
        *,
        strict: bool = False,
    ) -> None:
        self.type = update_type
        self.callback = callback
        self.strict = strict

    def check_update(self, update: object) -> TypeGuard[T]:
        return type(update) is self.type if self.strict else isinstance(update, self.type)

    async def handle_update(self, update: T, context: Context) -> None:
        await self.callback(update, context)

    async def _dispatch(self, update: object, context: Context) -> bool:
        if not self.check_update(update):
            return False
        await self.handle_update(update, context)
        return True


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
