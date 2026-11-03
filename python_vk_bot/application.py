"""Serial queued dispatch, managed tasks, and explicit resource ownership."""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import aclosing, suppress
from types import TracebackType
from typing import Self

from .bot import Bot
from .context import Context
from .errors import ApplicationHandlerStop, LifecycleError
from .handlers import Handler, TypeHandler, _DispatchHandler
from .long_poll import LongPoll
from .models import Update
from .queues import UpdateQueue, _QueueItem

type ErrorCallback = Callable[[Update | None, Context], Awaitable[None]]
type LifecycleHook = Callable[[Application], Awaitable[None]]

logger = logging.getLogger(__name__)


async def _await_owned[T](task: asyncio.Future[T]) -> T:
    """Finish owned cleanup even on repeated caller cancellation, then propagate it."""
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
        except BaseException:
            break
    if interrupted:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    return task.result()


class Application:
    def __init__(
        self,
        bot: Bot,
        group_id: int,
        *,
        deduplication_size: int = 4096,
        update_queue_size: int = 256,
        post_init: LifecycleHook | None = None,
        post_stop: LifecycleHook | None = None,
        post_shutdown: LifecycleHook | None = None,
    ) -> None:
        if group_id <= 0 or deduplication_size < 0:
            raise ValueError("group_id must be positive and deduplication_size nonnegative")
        self.bot = bot
        self.group_id = group_id
        self.bot_data: dict[str, object] = {}
        self.user_data: dict[int, dict[str, object]] = {}
        self.peer_data: dict[int, dict[str, object]] = {}
        self._handlers: dict[int, list[_DispatchHandler]] = {}
        self._error_handlers: list[ErrorCallback] = []
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._deduplication_size = deduplication_size
        self._post_init = post_init
        self._post_stop = post_stop
        self._post_shutdown = post_shutdown
        self._lifecycle_lock = asyncio.Lock()
        self._initialized = False
        self._context_active = False
        self._running = False
        self._started = False
        self._queue_open = False
        self._post_stop_pending = False
        self._update_queue = UpdateQueue(self, update_queue_size)
        self._tasks: dict[asyncio.Task[object], bool] = {}
        self._polling_task: asyncio.Task[None] | None = None
        self._polling_waiting = False
        self._polling_cancel_requested = False
        self._consumer_task: asyncio.Task[None] | None = None
        self._processing_task: asyncio.Task[bool] | None = None
        self._finishing_handler: asyncio.Task[bool] | None = None
        self._hook_task: asyncio.Task[object] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._shutdown_task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def update_queue(self) -> UpdateQueue:
        """The current run's producer interface; only Application consumes events."""
        return self._update_queue

    def _check_lifecycle(self, *, stopping: bool = False) -> None:
        current = asyncio.current_task()
        if current is self._hook_task:
            raise LifecycleError("Lifecycle hooks cannot recursively invoke lifecycle methods")
        if not stopping and (current is self._processing_task or current in self._tasks):
            raise LifecycleError(
                "Use stop() inside a handler or task; shutdown belongs to the owner"
            )

    def add_handler[T](self, handler: Handler | TypeHandler[T], *, group: int = 0) -> None:
        if self._started:
            raise LifecycleError("Register handlers before starting the application")
        self._handlers.setdefault(group, []).append(handler)

    def add_error_handler(self, callback: ErrorCallback) -> None:
        if self._started:
            raise LifecycleError("Register error handlers before starting the application")
        self._error_handlers.append(callback)

    async def _call_hook(self, hook: LifecycleHook | None) -> None:
        if hook is None:
            return
        self._hook_task = asyncio.current_task()
        try:
            await hook(self)
        finally:
            self._hook_task = None

    async def initialize(self) -> None:
        self._check_lifecycle()
        if self._shutdown_task is not None and not self._shutdown_task.done():
            raise LifecycleError("Application shutdown is in progress")
        self._shutdown_task = None
        async with self._lifecycle_lock:
            if self._initialized:
                return
            try:
                await self.bot.initialize()
                await self._call_hook(self._post_init)
            except BaseException:
                cleanup = asyncio.create_task(self.bot.shutdown(), name="vk-startup-cleanup")
                try:
                    await _await_owned(cleanup)
                except BaseException as error:
                    logger.error("Startup cleanup failed (%s)", type(error).__name__)
                raise
            self._initialized = True

    async def start(self) -> None:
        self._check_lifecycle()
        if not self._initialized:
            raise LifecycleError("Initialize the application before starting it")
        if self._shutdown_task is not None:
            raise LifecycleError("Application shutdown is in progress")
        if self._running:
            return
        if self._started:
            raise LifecycleError("Shut down and initialize before starting another run")
        if self._update_queue._closed:
            self._update_queue = UpdateQueue(self, self._update_queue.maxsize)
        self._stop_task = None
        self._finishing_handler = None
        self._queue_open = True
        self._running = True
        self._started = True
        self._post_stop_pending = True
        self._consumer_task = asyncio.create_task(self._consume(), name="vk-update-consumer")

    async def stop(self) -> None:
        """Stop intake and drain accepted work. Does not invoke post_stop or close Bot.

        Inside a handler or managed task this requests stopping without awaiting
        that same task. An external owner can await stop/shutdown for completion.
        """
        self._check_lifecycle(stopping=True)
        if not self._started:
            return
        if self._stop_task is None:
            self._running = False
            self._finishing_handler = self._processing_task
            self._update_queue._space.set()
            self._stop_task = asyncio.create_task(self._stop(), name="vk-application-stop")
        current = asyncio.current_task()
        if current is self._processing_task or current in self._tasks:
            return
        await _await_owned(self._stop_task)

    async def _stop(self) -> None:
        # Polling awaiting a receipt must finish it; cancelling it would cancel
        # the active handler. Only interrupt polling that is acquiring updates.
        polling = self._polling_task
        if polling is not None:
            if not self._polling_waiting:
                self._cancel_polling(polling)
            await asyncio.gather(polling, return_exceptions=True)
        if self._finishing_handler is not None:
            await asyncio.gather(self._finishing_handler, return_exceptions=True)
        tasks = tuple(self._tasks)
        for task in tasks:
            if self._tasks.get(task):
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._queue_open = False
        self._update_queue._close()
        if self._consumer_task is not None:
            await self._consumer_task
        self._finishing_handler = None

    async def shutdown(self) -> None:
        """Drain, invoke post_stop once, close Bot, then invoke post_shutdown."""
        self._check_lifecycle()
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._shutdown(), name="vk-application-shutdown"
            )
        await _await_owned(self._shutdown_task)

    async def _shutdown(self) -> None:
        # Wait for initialization, but never retain this lock while waiting for
        # handlers/tasks: their lifecycle requests are rejected or request stop.
        async with self._lifecycle_lock:
            initialized = self._initialized
        if not initialized:
            return
        failure: BaseException | None = None
        try:
            await self.stop()
        except BaseException as error:
            failure = error
        if self._post_stop_pending:
            self._post_stop_pending = False
            try:
                await self._call_hook(self._post_stop)
            except BaseException as error:
                if failure is None:
                    failure = error
                else:
                    logger.error("Post-stop hook failed (%s)", type(error).__name__)
        try:
            await self.bot.shutdown()
        except BaseException as error:
            if failure is None:
                failure = error
            else:
                logger.error("Bot shutdown failed (%s)", type(error).__name__)
        finally:
            self._initialized = False
        try:
            await self._call_hook(self._post_shutdown)
        except BaseException as error:
            if failure is None:
                failure = error
            else:
                logger.error("Post-shutdown hook failed (%s)", type(error).__name__)
        finally:
            self._started = False
        if failure is not None:
            raise failure

    async def __aenter__(self) -> Self:
        if self._initialized or self._context_active:
            raise LifecycleError("Application context managers cannot be nested")
        self._context_active = True
        try:
            await self.initialize()
            await self.start()
        except BaseException:
            try:
                await self.shutdown()
            except BaseException as error:
                logger.error("Application startup cleanup failed (%s)", type(error).__name__)
            finally:
                self._context_active = False
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            await self.shutdown()
        except BaseException as error:
            if exc is None:
                raise
            logger.error("Application cleanup failed (%s)", type(error).__name__)
        finally:
            self._context_active = False

    def _check_enqueue(self, queue: UpdateQueue, item: _QueueItem) -> None:
        current = asyncio.current_task()
        finishing = current is self._finishing_handler or current in self._tasks
        if (
            queue is not self._update_queue
            or not self._queue_open
            or not (self._running or finishing)
        ):
            raise LifecycleError("Application is not running or accepting events")
        if isinstance(item.event, Update):
            if item.event.group_id != self.group_id:
                raise ValueError("Update belongs to another community")
            if item.user_id is not None or item.peer_id is not None:
                raise ValueError("VK update state scopes are supplied by the update")

    def _context(self, item: _QueueItem, error: Exception | None = None) -> Context:
        event = item.event
        user_id = event.user_id if isinstance(event, Update) else item.user_id
        peer_id = event.peer_id if isinstance(event, Update) else item.peer_id
        return Context(
            application=self,
            bot=self.bot,
            user_data=self.user_data.setdefault(user_id, {}) if user_id is not None else {},
            peer_data=self.peer_data.setdefault(peer_id, {}) if peer_id is not None else {},
            bot_data=self.bot_data,
            error=error,
            event=event,
        )

    async def _report_error(self, item: _QueueItem, error: Exception) -> None:
        context = self._context(item, error)
        update = item.event if isinstance(item.event, Update) else None
        logger.error("Event processing failed (%s)", type(error).__name__)
        for callback in self._error_handlers:
            try:
                await callback(update, context)
            except ApplicationHandlerStop:
                break
            except Exception as callback_error:
                logger.error("Error handler failed (%s)", type(callback_error).__name__)

    async def process_update(
        self, update: object, *, user_id: int | None = None, peer_id: int | None = None
    ) -> bool:
        """Queue and await dispatch; False for a duplicate, otherwise True.

        Cancellation skips queued work or cancels/awaits the active handler.
        Internal objects can explicitly select user/peer state scopes.
        """
        if self._processing_task is asyncio.current_task():
            raise LifecycleError("Recursive update dispatch is not supported")
        return await self._submit(_QueueItem(update, user_id, peer_id))

    async def _submit(self, item: _QueueItem) -> bool:
        receipt = asyncio.get_running_loop().create_future()
        item.receipt = receipt
        try:
            await self._update_queue._put(item)
            return await asyncio.shield(receipt)
        except asyncio.CancelledError:
            item.cancelled = True
            if receipt.done() and not receipt.cancelled():
                receipt.exception()
            receipt.cancel()
            if item.task is not None and not item.task.done():
                item.task.cancel()
                with suppress(BaseException):
                    await _await_owned(item.task)
            raise

    async def _consume(self) -> None:
        while True:
            try:
                item = await self._update_queue._get()
            except asyncio.QueueShutDown:
                return
            try:
                if item.cancelled:
                    continue
                task = asyncio.create_task(self._dispatch(item), name="vk-event-dispatch")
                item.task = task
                self._processing_task = task
                try:
                    result = await task
                except asyncio.CancelledError:
                    if item.receipt is not None and not item.receipt.done():
                        item.receipt.cancel()
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise
                except Exception as error:
                    if item.receipt is not None and not item.receipt.done():
                        item.receipt.set_exception(error)
                else:
                    if item.receipt is not None and not item.receipt.done():
                        item.receipt.set_result(result)
                finally:
                    self._processing_task = None
            finally:
                self._update_queue._queue.task_done()

    async def _dispatch(self, item: _QueueItem) -> bool:
        if item.error is not None:
            await self._report_error(item, item.error)
            return True
        event = item.event
        if isinstance(event, Update):
            if event.group_id != self.group_id:
                raise ValueError("Update belongs to another community")
            if event.event_id in self._seen:
                return False
        try:
            context = self._context(item)
            for group in sorted(self._handlers):
                for handler in self._handlers[group]:
                    if await handler._dispatch(event, context):
                        break
        except ApplicationHandlerStop:
            pass
        except Exception as error:
            await self._report_error(item, error)
            raise
        if isinstance(event, Update) and self._deduplication_size:
            self._seen[event.event_id] = None
            if len(self._seen) > self._deduplication_size:
                self._seen.popitem(last=False)
        return True

    def create_task[T](
        self,
        coroutine: Coroutine[object, object, T],
        *,
        update: object = None,
        name: str | None = None,
        cancel_on_stop: bool = False,
    ) -> asyncio.Task[T]:
        """Own a running coroutine, report failures serially, and await it on stop.

        Use cancel_on_stop for long-lived workers. Tasks must not directly mutate
        Context state or be awaited by a handler if they depend on the consumer.
        """
        if not self._running:
            coroutine.close()
            raise LifecycleError("Create tasks only while the application is running")
        if isinstance(update, Update) and update.group_id != self.group_id:
            coroutine.close()
            raise ValueError("Update belongs to another community")

        async def run() -> T:
            try:
                return await coroutine
            except Exception as error:
                try:
                    await self._submit(_QueueItem(update, error=error))
                except Exception as reporting_error:
                    logger.error("Task error reporting failed (%s)", type(reporting_error).__name__)
                raise

        task = asyncio.create_task(run(), name=name)
        self._tasks[task] = cancel_on_stop

        def finished(done: asyncio.Task[T]) -> None:
            self._tasks.pop(done, None)
            # Also close a coroutine cancelled before the wrapper's first step.
            coroutine.close()
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)
        return task

    async def _poll(self, long_poll: LongPoll) -> None:
        async with aclosing(long_poll.listen()) as updates:
            async for update in updates:
                if not self._running:
                    break
                self._polling_waiting = True
                try:
                    await self.process_update(update)
                except Exception:
                    logger.warning("Skipping failed update in polling mode")
                finally:
                    self._polling_waiting = False
                if not self._running:
                    break

    def _cancel_polling(self, task: asyncio.Task[None]) -> None:
        """Request cancellation once; another owner must await the same cleanup."""
        if not self._polling_cancel_requested and not task.done():
            self._polling_cancel_requested = True
            task.cancel()

    async def run_polling(self, *, wait: int = 25) -> None:
        """Run until stop/cancellation; own lifecycle, not the caller's event loop."""
        if self._polling_task is not None:
            raise LifecycleError("Polling is already running")
        long_poll = LongPoll(self.bot, self.group_id, wait=wait)
        async with self:
            task = asyncio.create_task(self._poll(long_poll), name="vk-long-poll")
            self._polling_task = task
            self._polling_cancel_requested = False
            try:
                await asyncio.wait({task})
                if not task.cancelled():
                    task.result()
            except Exception as error:
                await self._submit(_QueueItem(None, error=error))
                raise
            finally:
                try:
                    self._cancel_polling(task)
                    await _await_owned(asyncio.gather(task, return_exceptions=True))
                finally:
                    self._polling_task = None
