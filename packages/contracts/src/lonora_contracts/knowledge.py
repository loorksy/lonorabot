"""Knowledge entries of one agent (owner decision Q40): semantic notes and links."""

from typing import Literal

from pydantic import Field, field_validator

from .domain import Contract


class KnowledgeLink(Contract):
    """A «رابط» entry: a public page the agent may read through its public client."""

    title: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=1, max_length=2000)
    note: str = Field(default="", max_length=4000)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("knowledge_link_url_invalid")
        return value.strip()


class KnowledgeNote(Contract):
    """A «ملاحظة» entry, stored as one semantic note of the agent's memory."""

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=8000)


class KnowledgeItem(Contract):
    id: str
    type: Literal["note", "link"]
    title: str
    content: str
    url: str | None = None
    version: int | None = None
    updated_at: str
