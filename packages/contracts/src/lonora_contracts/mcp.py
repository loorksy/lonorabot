from typing import Literal

from pydantic import ConfigDict, Field

from .domain import Contract


class McpConnection(Contract):
    name: str = Field(min_length=1, max_length=80)
    transport: Literal["http", "stdio"] = "http"
    url: str | None = None
    command: list[str] = Field(default_factory=list[str], max_length=16)
    secret_id: str | None = None
    enabled: bool = False


class McpToolDeclaration(Contract):
    """Operator-reviewed authority, never supplied by remote tools or owner CRUD."""

    model_config = ConfigDict(frozen=True)

    owner_id: str = Field(min_length=1, max_length=80)
    connection_id: str = Field(min_length=1, max_length=80)
    endpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_name: str = Field(min_length=1, max_length=128)
    input_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect: Literal["read_only"] = "read_only"
    credential_scope: Literal["integration"] = "integration"
