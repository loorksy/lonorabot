from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from .domain import Contract


class AppOpen(Contract):
    """The owner opened the app (or brought it to the front) on a device in this zone."""

    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError, OSError) as error:
            raise ValueError("invalid_timezone") from error
        return value
