"""Bounded, application-owned event admission; only Application consumes events."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .application import Application


class _QueueClosed(Exception):
    """Private signal: the closed queue has drained."""


@dataclass
class _QueueItem:
    event: object
    user_id: Optional[int] = None
    peer_id: Optional[int] = None
    error: Optional[Exception] = field(default=None, repr=False)
    receipt: Optional[asyncio.Future[bool]] = field(default=None, repr=False)
    task: Optional[asyncio.Task[bool]] = field(default=None, repr=False)
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
        self._maxsize = maxsize
        self._closed = False

    @cached_property
    def _queue(self) -> asyncio.Queue[_QueueItem]:
        queue = asyncio.Queue[_QueueItem](self._maxsize)
        return queue

    @cached_property
    def _space(self) -> asyncio.Event:
        return asyncio.Event()

    @cached_property
    def _available(self) -> asyncio.Event:
        return asyncio.Event()

    @property
    def maxsize(self) -> int:
        return self._maxsize

    def qsize(self) -> int:
        return self._queue.qsize() if "_queue" in self.__dict__ else 0

    def empty(self) -> bool:
        return self.qsize() == 0

    def full(self) -> bool:
        return self.qsize() >= self.maxsize

    async def put(
        self, update: object, *, user_id: Optional[int] = None, peer_id: Optional[int] = None
    ) -> None:
        """Enqueue an event, waiting for capacity; does not wait for dispatch."""
        await self._put(_QueueItem(update, user_id, peer_id))

    def put_nowait(
        self, update: object, *, user_id: Optional[int] = None, peer_id: Optional[int] = None
    ) -> None:
        """Enqueue an event or raise QueueFull/LifecycleError without waiting."""
        self._put_nowait(_QueueItem(update, user_id, peer_id))

    def _put_nowait(self, item: _QueueItem) -> None:
        self._application._check_enqueue(self, item)
        self._queue.put_nowait(item)
        self._available.set()

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
        while True:
            self._available.clear()
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                if self._closed:
                    raise _QueueClosed from None
                await self._available.wait()
            else:
                self._space.set()
                return item

    def _close(self) -> None:
        self._closed = True
        self._available.set()
        self._space.set()
