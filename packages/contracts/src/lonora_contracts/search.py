from pydantic import Field

from .domain import Contract


class SearchQuery(Contract):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=30, ge=1, le=100)
