"""Owner-defined chat lists (WP-B): named sets of conversations used as list filters."""

from pydantic import Field, field_validator

from .domain import Contract


class ChatListCreate(Contract):
    name: str = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("chat_list_name_required")
        return value


class ChatListUpdate(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    position: int | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if not value:
            raise ValueError("chat_list_name_required")
        return value


class ChatListMembers(Contract):
    thread_ids: list[str] = Field(max_length=500)

    @field_validator("thread_ids")
    @classmethod
    def unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))
