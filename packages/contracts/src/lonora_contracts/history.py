from pydantic import Field

from .domain import Contract


class HistoryPage(Contract):
    before_seq: int | None = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=200)
