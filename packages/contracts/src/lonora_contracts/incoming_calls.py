"""Incoming conversation invitations never carry execution authority."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .domain import Contract

# How the owner wants to be reached about something that needs him (the reach-me
# preference of the owner profile). Delivery is in-app until off-app delivery exists:
# activity = keep it in Activity only; notify = an attention item; message = a message
# in the agent's conversation; call = an incoming conversation invitation.
ReachMe = Literal["activity", "notify", "message", "call"]
REACH_ME_CHANNELS: tuple[ReachMe, ...] = ("activity", "notify", "message", "call")


class IncomingCallPolicy(Contract):
    """The owner's reach-me preference; invitations ring only when it is ``call``."""

    channel: ReachMe = "message"
    enabled: bool = False
    device_id: str | None = None
    opportunities: bool = False
    action_required: bool = False
    critical: bool = True
    timezone: str = "UTC"
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    ttl_seconds: int = Field(default=45, ge=15, le=120)
    minimum_interval_seconds: int = Field(default=300, ge=60, le=86400)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("invalid_timezone") from error
        return value

    @model_validator(mode="after")
    def complete_policy(self) -> "IncomingCallPolicy":
        # One preference, never two that disagree: incoming calls are enabled exactly
        # when the owner chose to be called. A stored policy or client from before the
        # channel existed states only ``enabled``.
        if "channel" not in self.model_fields_set:
            self.channel = "call" if self.enabled else "message"
        elif "enabled" in self.model_fields_set and self.enabled != (self.channel == "call"):
            raise ValueError("incoming_call_channel_conflict")
        self.enabled = self.channel == "call"
        if self.enabled and not self.device_id:
            raise ValueError("incoming_call_device_required")
        if (self.quiet_start_hour is None) != (self.quiet_end_hour is None):
            raise ValueError("incoming_call_quiet_hours_incomplete")
        return self

    def quiet(self, now: datetime) -> bool:
        if self.quiet_start_hour is None or self.quiet_end_hour is None:
            return False
        hour = now.astimezone(ZoneInfo(self.timezone)).hour
        start, end = self.quiet_start_hour, self.quiet_end_hour
        return start <= hour < end if start < end else hour >= start or hour < end


class IncomingCallRequest(Contract):
    attention_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=8, max_length=400)


class IncomingCallAction(Contract):
    action: Literal["accept", "reject", "cancel"]
    device_id: str = Field(min_length=1, max_length=36)
