"""Bounded, application-owned event admission; only Application consumes events."""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .application import Application


@dataclass(slots=True)
class _QueueItem:
    event: object
    user_id: int | None = None
    peer_id: int | None = None
    error: Exception | None = field(default=None, repr=False)
    receipt: asyncio.Future[bool] | None = field(default=None, repr=False)
    task: asyncio.Task[bool] | None = field(default=None, repr=False)
    cancelled: bool = False


class UpdateQueue:
    """Producer interface to Application's FIFO, not a standalone asyncio.Queue.

    put waits for capacity outside handlers. In a handler, a full queue raises
    QueueFull instead of waiting for the consumer that is awaiting that handler.
    Items and their state scopes are process-local; no durable acceptance is implied.
    """

    def __init__(self, application: Application, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("update_queue_size must be positive")
        self._application = application
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize)
        self._space = asyncio.Event()
        self._closed = False

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize

    def qsize(self) -> int:
        return self._queue.qsize()

    def empty(self) -> bool:
        return self._queue.empty()

    def full(self) -> bool:
        return self._queue.full()

    async def put(
        self, update: object, *, user_id: int | None = None, peer_id: int | None = None
    ) -> None:
        """Enqueue an event, waiting for capacity; does not wait for dispatch."""
        await self._put(_QueueItem(update, user_id, peer_id))

    def put_nowait(
        self, update: object, *, user_id: int | None = None, peer_id: int | None = None
    ) -> None:
        """Enqueue an event or raise QueueFull/LifecycleError without waiting."""
        self._put_nowait(_QueueItem(update, user_id, peer_id))

    def _put_nowait(self, item: _QueueItem) -> None:
        self._application._check_enqueue(self, item)
        self._queue.put_nowait(item)

    async def _put(self, item: _QueueItem) -> None:
        while True:
            try:
                self._put_nowait(item)
                return
            except asyncio.QueueFull:
                if self._application._processing_task is asyncio.current_task():
                    raise
                self._space.clear()
                await self._space.wait()

    async def _get(self) -> _QueueItem:
        item = await self._queue.get()
        self._space.set()
        return item

    def _close(self) -> None:
        self._closed = True
        self._queue.shutdown()
        self._space.set()
