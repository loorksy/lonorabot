from pydantic import Field

from .domain import Contract


class ArtifactCreate(Contract):
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=5000000)
    media_type: str = "text/plain"
    thread_id: str | None = None
