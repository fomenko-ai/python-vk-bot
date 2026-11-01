"""Small synchronous predicates; filter execution must not perform blocking I/O."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Union

from .models import Update


class Filter:
    def __init__(self, predicate: Callable[[Update], bool]) -> None:
        self.predicate = predicate

    def __call__(self, update: Update) -> bool:
        return self.predicate(update)

    def __and__(self, other: Filter) -> Filter:
        return Filter(lambda update: self(update) and other(update))

    def __or__(self, other: Filter) -> Filter:
        return Filter(lambda update: self(update) or other(update))

    def __invert__(self) -> Filter:
        return Filter(lambda update: not self(update))


class Regex(Filter):
    """Search the message text using a compiled regular expression."""

    def __init__(self, pattern: Union[str, re.Pattern[str]]) -> None:
        compiled = re.compile(pattern)
        super().__init__(
            lambda update: (
                update.message is not None and compiled.search(update.message.text) is not None
            )
        )


ALL = Filter(lambda update: True)
TEXT = Filter(lambda update: update.message is not None and bool(update.message.text))
LOCATION = Filter(lambda update: update.message is not None and update.message.geo is not None)
