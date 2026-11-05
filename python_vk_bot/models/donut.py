"""Typed facts from VK Donut subscription events, not subscription or access state."""

from __future__ import annotations

import sys
from typing import Optional

from pydantic import Field

from .base import VKModel

if sys.version_info >= (3, 11):
    from enum import StrEnum as _StrEnum
else:
    from enum import Enum

    class _StrEnum(str, Enum):
        """String-valued enums with value-based str() on Python 3.9/3.10."""

        def __str__(self) -> str:
            return str(self.value)


class DonutSubscriptionEventType(_StrEnum):
    """The five supported VK Callback subscription event names."""

    CREATE = "donut_subscription_create"
    PROLONGED = "donut_subscription_prolonged"
    CANCELLED = "donut_subscription_cancelled"
    EXPIRED = "donut_subscription_expired"
    PRICE_CHANGED = "donut_subscription_price_changed"


class DonutSubscriptionEvent(VKModel):
    """Shared view of a Donut event object; amounts are in rubles.

    Monetary fields depend on the event type and default to None when absent.
    Unknown fields are retained. This object carries no inferred payment dates
    or entitlement status; cancellation does not itself mean access has expired.
    """

    user_id: int = Field(strict=True, gt=0)
    amount: Optional[int] = Field(default=None, strict=True)
    amount_without_fee: Optional[float] = Field(default=None, strict=True, allow_inf_nan=False)
    amount_old: Optional[int] = Field(default=None, strict=True)
    amount_new: Optional[int] = Field(default=None, strict=True)
    amount_diff: Optional[float] = Field(default=None, strict=True, allow_inf_nan=False)
    amount_diff_without_fee: Optional[float] = Field(default=None, strict=True, allow_inf_nan=False)
