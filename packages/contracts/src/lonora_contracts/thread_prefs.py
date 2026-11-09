"""The owner's per-conversation state (WP-A): read cursor, marks, pins and the list setting.

Every field is per owner on the server and shared by web and mobile. ``pinned`` is a
request; the server assigns ``pinned_order`` (1..3, newest on top) and refuses a fourth
pin with ``thread_pin_limit``.
"""

from pydantic import Field, model_validator

from .domain import Contract


class ThreadPrefsUpdate(Contract):
    pinned: bool | None = None
    muted: bool | None = None
    archived: bool | None = None
    favourite: bool | None = None
    marked_unread: bool | None = None

    @model_validator(mode="after")
    def something_changes(self) -> "ThreadPrefsUpdate":
        if not self.model_fields_set.intersection(
            {"pinned", "muted", "archived", "favourite", "marked_unread"}
        ):
            raise ValueError("thread_prefs_empty")
        return self


class ThreadPrefsBulkUpdate(ThreadPrefsUpdate):
    thread_ids: list[str] = Field(min_length=1, max_length=200)


class ReadCursor(Contract):
    seq: int = Field(ge=0)


class ThreadSettings(Contract):
    """«إبقاء المحادثات مؤرشفة»: when false an archived conversation returns to the list
    on a new message."""

    keep_archived: bool = True
