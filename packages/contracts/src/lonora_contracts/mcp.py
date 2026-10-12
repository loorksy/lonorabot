from typing import Literal

from pydantic import Field

from .domain import Contract


class McpConnection(Contract):
    name: str = Field(min_length=1, max_length=80)
    transport: Literal["http", "stdio"] = "http"
    url: str | None = None
    command: list[str] = Field(default_factory=list, max_length=16)
    secret_id: str | None = None
    enabled: bool = False
