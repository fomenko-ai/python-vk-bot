"""Outgoing actions for replies to VK message_event callbacks."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShowSnackbar(BaseModel):
    """Show a notification containing at most 90 characters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, hide_input_in_errors=True)

    type: Literal["show_snackbar"] = "show_snackbar"
    text: str = Field(max_length=90, repr=False)
