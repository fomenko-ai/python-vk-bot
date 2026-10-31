"""State scopes for one dispatched update."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .bot import Bot

if TYPE_CHECKING:
    from .application import Application


@dataclass(slots=True)
class Context:
    application: Application
    bot: Bot
    user_data: dict[str, object]
    peer_data: dict[str, object]
    bot_data: dict[str, object]
    error: Exception | None = field(default=None, repr=False)
