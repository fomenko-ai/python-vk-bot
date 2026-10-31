"""VK Bots Long Poll recovery without recursion or detached tasks."""

import asyncio
import logging
from collections.abc import AsyncGenerator

from pydantic import ValidationError

from .bot import Bot
from .errors import HTTPError, InvalidResponseError, NetworkError, RateLimitError
from .models.api import LongPollResponse, LongPollServer
from .models.events import Update

logger = logging.getLogger(__name__)


class LongPoll:
    def __init__(self, bot: Bot, group_id: int, *, wait: int = 25) -> None:
        if group_id <= 0:
            raise ValueError("group_id must be positive")
        if not 1 <= wait <= 90:
            raise ValueError("wait must be between 1 and 90 seconds")
        self.bot = bot
        self.group_id = group_id
        self.wait = wait
        self._server: LongPollServer | None = None

    async def _connect(self, *, preserve_ts: bool = False) -> None:
        old_ts = self._server.ts if self._server is not None else None
        server = await self.bot.get_long_poll_server(self.group_id)
        if preserve_ts and old_ts is not None:
            server.ts = old_ts
        self._server = server

    async def get_updates(self) -> list[Update]:
        """Fetch a batch; the caller owns dispatch and its failure policy."""
        if self._server is None:
            await self._connect()
        server = self._server
        if server is None:
            raise InvalidResponseError("Long Poll connection is unavailable")
        payload = await self.bot.transport.poll(
            server.server, key=server.key, ts=server.ts, wait=self.wait
        )
        try:
            response = LongPollResponse.model_validate(payload)
        except ValidationError:
            raise InvalidResponseError("Invalid Long Poll response") from None
        if response.failed == 1:
            if response.ts is None:
                raise InvalidResponseError("Long Poll recovery has no cursor")
            server.ts = response.ts
            logger.warning("Long Poll event history was partially lost")
            return []
        if response.failed in (2, 3):
            await self._connect(preserve_ts=response.failed == 2)
            return []
        if response.failed is not None:
            raise InvalidResponseError("Unknown Long Poll failure code")
        if response.ts is None or response.updates is None:
            raise InvalidResponseError("Long Poll response has no cursor or updates")
        # Validate the whole batch before advancing the cursor; malformed data is fatal.
        updates = [Update.from_dict(item) for item in response.updates]
        if any(update.group_id != self.group_id for update in updates):
            raise InvalidResponseError("Long Poll event belongs to another community")
        server.ts = response.ts
        return updates

    async def listen(self) -> AsyncGenerator[Update]:
        """Retry only polling/network acquisition; authentication errors propagate."""
        delay = 1.0
        while True:
            try:
                updates = await self.get_updates()
            except HTTPError as error:
                if error.status_code != 429 and error.status_code < 500:
                    raise
                updates = None
            except NetworkError, RateLimitError:
                updates = None
            if updates is None:
                logger.warning("Long Poll temporarily unavailable; reconnecting")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
                continue
            delay = 1.0
            for update in updates:
                yield update
            if not updates:
                # Local anti-spin policy, not a VK rate limit.
                await asyncio.sleep(0.1)
