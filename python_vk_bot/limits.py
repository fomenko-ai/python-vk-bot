"""Keyboard limits for VK API 5.199; see docs/development/api-compatibility.md."""

from typing import Final

MAX_INLINE_BUTTONS: Final[int] = 10
MAX_REPLY_BUTTONS: Final[int] = 40
MAX_BUTTONS_PER_ROW: Final[int] = 5
MAX_INLINE_ROWS: Final[int] = 6
MAX_REPLY_ROWS: Final[int] = 10
MAX_BUTTON_LABEL_LENGTH: Final[int] = 40
MAX_LOCATION_ROW_BUTTONS: Final[int] = 2
MAX_VKPAY_ROW_BUTTONS: Final[int] = 1
