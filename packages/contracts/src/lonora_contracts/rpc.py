from typing import Any

from pydantic import Field

from .domain import Contract


class RpcRequest(Contract):
    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class RpcError(Contract):
    code: str
    request_id: str | None = None
