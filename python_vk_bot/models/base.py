"""Shared inbound-model policy."""

from pydantic import BaseModel, ConfigDict


class VKModel(BaseModel):
    """Retain unmodeled VK fields without logging their contents."""

    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)
