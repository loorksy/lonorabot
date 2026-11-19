from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .domain import Contract


class McpOAuth(Contract):
    """A server Lonora signed in to (OAuth, VISION.md 13.1): where and how its access
    token is renewed. The tokens are workspace secrets: the access token is the
    connection's ``secret_id``, the refresh token ``refresh_secret_id``, and a client
    secret the server issued ``client_secret_id``. ``resource_secret_id`` holds the
    identifier the server published for itself when it is not its address: it shares the
    address's origin and may share its key, so it is kept in the store too. None means
    the address."""

    issuer: str = Field(min_length=1, max_length=2048)
    token_endpoint: str = Field(min_length=1, max_length=2048)
    resource_secret_id: str | None = None
    client_id: str = Field(min_length=1, max_length=8192)
    client_method: Literal["none", "client_secret_basic", "client_secret_post"] = "none"
    client_secret_id: str | None = None
    refresh_secret_id: str | None = None
    expires_at: datetime | None = None

    @field_validator("issuer", "token_endpoint")
    @classmethod
    def https_only(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().startswith("https://"):
            raise ValueError("mcp_https_required")
        return value

    @model_validator(mode="after")
    def client_secret(self) -> "McpOAuth":
        if (self.client_method == "none") != (self.client_secret_id is None):
            raise ValueError("mcp_oauth_client_invalid")
        return self


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
    # Signed in with OAuth from a Secret card: its access token is ``secret_id``.
    oauth: McpOAuth | None = None
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
        # Only a card-saved server is signed in to, and its access token is its secret.
        if self.oauth is not None and (not stored or self.secret_id is None):
            raise ValueError("mcp_oauth_invalid")
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
