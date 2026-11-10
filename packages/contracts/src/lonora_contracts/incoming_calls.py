"""Incoming conversation invitations never carry execution authority."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .domain import Contract

# How the owner wants to be reached about something that needs him (the reach-me
# preference of the owner profile). Delivery is in-app until off-app delivery exists:
# activity = keep it in Activity only; notify = the inbox (Agents raise their own alerts
# once owner_notify exists; until then they message); message = a message
# in the agent's conversation; call = an incoming conversation invitation.
ReachMe = Literal["activity", "notify", "message", "call"]
REACH_ME_CHANNELS: tuple[ReachMe, ...] = ("activity", "notify", "message", "call")
# Codes of IncomingCallPolicy's checks that tell the owner what to fix; the API returns
# them as the error code instead of a generic invalid_request.
POLICY_ERROR_CODES = frozenset(
    {
        "incoming_call_channel_conflict",
        "incoming_call_device_required",
        "incoming_call_quiet_hours_incomplete",
        "invalid_timezone",
    }
)


def policy_error_code(errors: Iterable[Mapping[str, Any]]) -> str:
    """The first owner-actionable policy code among validation errors, else invalid_request."""
    for item in errors:
        cause = str(item.get("ctx", {}).get("error", ""))
        if item.get("type") == "value_error" and cause in POLICY_ERROR_CODES:
            return cause
    return "invalid_request"


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
    # Owner decision Q47: quiet hours to the minute (minutes after local midnight). The
    # whole-hour fields stay for clients that only know hours and always follow these.
    quiet_start_minute: int | None = Field(default=None, ge=0, le=1439)
    quiet_end_minute: int | None = Field(default=None, ge=0, le=1439)
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
        self._align_quiet_minutes()
        if (self.quiet_start_minute is None) != (self.quiet_end_minute is None):
            raise ValueError("incoming_call_quiet_hours_incomplete")
        return self

    def _align_quiet_minutes(self) -> None:
        """Hours and minutes describe one window. A client that sends only hours (or an hour
        that disagrees with a stored minute) sets the minute on the hour; clearing the hours
        clears the window."""
        hours_sent = {"quiet_start_hour", "quiet_end_hour"} & self.model_fields_set
        if hours_sent and self.quiet_start_hour is None and self.quiet_end_hour is None:
            self.quiet_start_minute = self.quiet_end_minute = None
            return
        for side in ("start", "end"):
            hour: int | None = getattr(self, f"quiet_{side}_hour")
            minute: int | None = getattr(self, f"quiet_{side}_minute")
            if hour is not None and (minute is None or minute // 60 != hour):
                setattr(self, f"quiet_{side}_minute", hour * 60)
            elif hour is None and minute is not None:
                setattr(self, f"quiet_{side}_hour", minute // 60)

    def quiet(self, now: datetime) -> bool:
        if self.quiet_start_minute is None or self.quiet_end_minute is None:
            return False
        local = now.astimezone(ZoneInfo(self.timezone))
        minute = local.hour * 60 + local.minute
        start, end = self.quiet_start_minute, self.quiet_end_minute
        return start <= minute < end if start < end else minute >= start or minute < end

    def quiet_until(self, now: datetime) -> datetime | None:
        """When the current quiet hours end, or None outside them."""
        if not self.quiet(now) or self.quiet_end_minute is None:
            return None
        local = now.astimezone(ZoneInfo(self.timezone))
        end = local.replace(
            hour=self.quiet_end_minute // 60,
            minute=self.quiet_end_minute % 60,
            second=0,
            microsecond=0,
        )
        if end <= local:
            end += timedelta(days=1)
        return end.astimezone(UTC)


class IncomingCallRequest(Contract):
    attention_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=8, max_length=400)


class IncomingCallAction(Contract):
    action: Literal["accept", "reject", "cancel"]
    device_id: str = Field(min_length=1, max_length=36)
