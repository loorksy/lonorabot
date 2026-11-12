from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .domain import Contract


class McpConnection(Contract):
    name: str = Field(min_length=1, max_length=80)
    transport: Literal["http", "stdio"] = "http"
    url: str | None = None
    # A server connected by a Secret card: its address (which may carry a key) is a
    # secret in the encrypted store, and the row keeps the address's fingerprint, which
    # the trust checks compare.
    url_secret_id: str | None = None
    endpoint_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    command: list[str] = Field(default_factory=list[str], max_length=16)
    secret_id: str | None = None
    enabled: bool = False

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str | None) -> str | None:
        # Remote servers only (Q56), over HTTPS: the transport refuses anything else anyway.
        if value is not None and not value.lower().startswith("https://"):
            raise ValueError("mcp_https_required")
        return value

    @model_validator(mode="after")
    def one_address(self) -> "McpConnection":
        stored = self.url_secret_id is not None
        if stored != (self.endpoint_sha256 is not None) or (stored and self.url is not None):
            raise ValueError("mcp_address_invalid")
        return self


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
