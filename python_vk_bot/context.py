"""State scopes for one dispatched update."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .bot import Bot

if TYPE_CHECKING:
    from .application import Application


@dataclass
class Context:
    application: Application
    bot: Bot
    user_data: dict[str, object]
    peer_data: dict[str, object]
    bot_data: dict[str, object]
    error: Optional[Exception] = field(default=None, repr=False)
