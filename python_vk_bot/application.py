"""Serial dispatch with explicit lifecycle and bounded duplicate suppression."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from functools import cached_property
from types import TracebackType
from typing import Optional

from typing_extensions import Self, TypeAlias

from .bot import Bot
from .context import Context
from .errors import LifecycleError
from .handlers import Handler
from .long_poll import LongPoll
from .models import Update

ErrorCallback: TypeAlias = Callable[[Optional[Update], Context], Awaitable[None]]
LifecycleHook: TypeAlias = Callable[["Application"], Awaitable[None]]

logger = logging.getLogger(__name__)


class Application:
    def __init__(
        self,
        bot: Bot,
        group_id: int,
        *,
        deduplication_size: int = 4096,
        post_init: Optional[LifecycleHook] = None,
        post_shutdown: Optional[LifecycleHook] = None,
    ) -> None:
        if group_id <= 0 or deduplication_size < 0:
            raise ValueError("group_id must be positive and deduplication_size nonnegative")
        self.bot = bot
        self.group_id = group_id
        self.bot_data: dict[str, object] = {}
        self.user_data: dict[int, dict[str, object]] = {}
        self.peer_data: dict[int, dict[str, object]] = {}
        self._handlers: dict[int, list[Handler]] = {}
        self._error_handlers: list[ErrorCallback] = []
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._deduplication_size = deduplication_size
        self._post_init = post_init
        self._post_shutdown = post_shutdown
        self._initialized = False
        self._context_active = False
        self._running = False
        self._polling_task: Optional[asyncio.Task[None]] = None
        self._processing_task: Optional[asyncio.Task[object]] = None

    # Python 3.9 binds locks at construction. First access must happen in async code,
    # since an ASGI application may be constructed before its event loop starts.
    @cached_property
    def _dispatch_lock(self) -> asyncio.Lock:
        return asyncio.Lock()

    @cached_property
    def _lifecycle_lock(self) -> asyncio.Lock:
        return asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running

    def add_handler(self, handler: Handler, *, group: int = 0) -> None:
        if self._running:
            raise LifecycleError("Register handlers before starting the application")
        self._handlers.setdefault(group, []).append(handler)

    def add_error_handler(self, callback: ErrorCallback) -> None:
        if self._running:
            raise LifecycleError("Register error handlers before starting the application")
        self._error_handlers.append(callback)

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            if self._initialized:
                return
            try:
                await self.bot.initialize()
                if self._post_init is not None:
                    await self._post_init(self)
            except BaseException:
                await self.bot.shutdown()
                raise
            self._initialized = True

    async def start(self) -> None:
        if not self._initialized:
            raise LifecycleError("Initialize the application before starting it")
        self._running = True

    async def stop(self) -> None:
        """Stop intake, cancel owned polling, and wait for active dispatch to finish.

        A handler may call stop: its current dispatch completes before polling exits.
        """
        self._running = False
        task = self._polling_task
        current = asyncio.current_task()
        if task is not None and task is not current:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._processing_task is not current:
            async with self._dispatch_lock:
                pass

    async def shutdown(self) -> None:
        if self._processing_task is asyncio.current_task():
            raise LifecycleError("Use stop() inside a handler; shutdown belongs to the owner")
        await self.stop()
        async with self._lifecycle_lock:
            if not self._initialized:
                return
            try:
                await self.bot.shutdown()
            finally:
                self._initialized = False
            if self._post_shutdown is not None:
                await self._post_shutdown(self)

    async def __aenter__(self) -> Self:
        if self._initialized or self._context_active:
            raise LifecycleError("Application context managers cannot be nested")
        self._context_active = True
        try:
            await self.initialize()
            await self.start()
        except BaseException:
            self._context_active = False
            raise
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        try:
            await self.shutdown()
        finally:
            self._context_active = False

    def _context(self, update: Optional[Update], error: Optional[Exception] = None) -> Context:
        user_id = update.user_id if update is not None else None
        peer_id = update.peer_id if update is not None else None
        return Context(
            application=self,
            bot=self.bot,
            user_data=self.user_data.setdefault(user_id, {}) if user_id is not None else {},
            peer_data=self.peer_data.setdefault(peer_id, {}) if peer_id is not None else {},
            bot_data=self.bot_data,
            error=error,
        )

    async def _report_error(self, update: Optional[Update], error: Exception) -> None:
        context = self._context(update, error)
        logger.error("Update processing failed (%s)", type(error).__name__)
        for callback in self._error_handlers:
            try:
                await callback(update, context)
            except Exception as callback_error:
                logger.error("Error handler failed (%s)", type(callback_error).__name__)

    async def process_update(self, update: Update) -> bool:
        """Return False for a duplicate, True after dispatch; propagate handler errors."""
        if self._processing_task is asyncio.current_task():
            raise LifecycleError("Recursive update dispatch is not supported")
        async with self._dispatch_lock:
            if not self._running:
                raise LifecycleError("Application is not running")
            if update.group_id != self.group_id:
                raise ValueError("Update belongs to another community")
            if update.event_id in self._seen:
                return False
            self._processing_task = asyncio.current_task()
            try:
                context = self._context(update)
                for group in sorted(self._handlers):
                    for handler in self._handlers[group]:
                        if handler.check_update(update):
                            await handler.handle_update(update, context)
                            break
            except Exception as error:
                await self._report_error(update, error)
                raise
            finally:
                self._processing_task = None
            if self._deduplication_size:
                self._seen[update.event_id] = None
                if len(self._seen) > self._deduplication_size:
                    self._seen.popitem(last=False)
            return True

    async def _poll(self, long_poll: LongPoll) -> None:
        updates = long_poll.listen()
        try:
            async for update in updates:
                if not self._running:
                    break
                try:
                    await self.process_update(update)
                except Exception:
                    # Dispatch already reported the error; never replay partial side effects.
                    logger.warning("Skipping failed update in polling mode")
                if not self._running:
                    break
        finally:
            await updates.aclose()

    async def run_polling(self, *, wait: int = 25) -> None:
        """Run until stop or cancellation; own startup and shutdown, not the event loop."""
        if self._polling_task is not None:
            raise LifecycleError("Polling is already running")
        long_poll = LongPoll(self.bot, self.group_id, wait=wait)
        async with self:
            task = asyncio.create_task(self._poll(long_poll), name="vk-long-poll")
            self._polling_task = task
            try:
                # Waiting does not forward caller cancellation to the child. A stop()
                # cancellation belongs to the child; external cancellation still propagates.
                await asyncio.wait({task})
                if not task.cancelled():
                    task.result()
            except Exception as error:
                await self._report_error(None, error)
                raise
            finally:
                try:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                finally:
                    self._polling_task = None
