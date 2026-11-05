"""Typed facts from VK Donut subscription events, not subscription or access state."""

from enum import StrEnum

from pydantic import Field

from .base import VKModel


class DonutSubscriptionEventType(StrEnum):
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
    amount: int | None = Field(default=None, strict=True)
    amount_without_fee: float | None = Field(default=None, strict=True, allow_inf_nan=False)
    amount_old: int | None = Field(default=None, strict=True)
    amount_new: int | None = Field(default=None, strict=True)
    amount_diff: float | None = Field(default=None, strict=True, allow_inf_nan=False)
    amount_diff_without_fee: float | None = Field(default=None, strict=True, allow_inf_nan=False)
