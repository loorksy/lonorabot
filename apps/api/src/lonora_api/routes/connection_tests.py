"""«اختبار الاتصال»: dry-run checks before the owner saves a connection (WP-H).

Each route makes one real, read-only round trip with the values the form holds and stores
nothing: no secret, no catalog, no connection row. A model provider lists its models, an
MCP server is initialised and lists its tools (reviewed like the trust preview), a broker
account reports its identity. None of them grants or widens any authority.
"""

import asyncio
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_adapters.mcp.connector import McpConnector
from lonora_adapters.mcp.policy import review_tools
from lonora_adapters.mcp.transport import HttpMcpTransport
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract
from lonora_contracts.model_catalog import ProviderCredential
from lonora_contracts.model_routing import ProviderId
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_providers.registry import model_adapter
from pydantic import Field

from ..middleware.auth import require_owner, runtime
from .providers import settings_provider

router = APIRouter()
# One bounded round trip: a test never hangs the form. The values are never logged or echoed.
TIMEOUT_SECONDS = 20


async def bounded[T](call: Awaitable[T]) -> T:
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            return await call
    except TimeoutError:
        raise LonoraError("connection_test_timeout", 504) from None


@router.post("/providers/{provider}/test")
async def dry_run_provider(
    body: ProviderCredential,
    provider: ProviderId = Depends(settings_provider),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    adapter = model_adapter(provider, body.api_key)
    try:
        models = await bounded(adapter.discover())
    finally:
        await adapter.close()
    return {"ok": True, "models": [model.id for model in models][:200]}


class McpTest(Contract):
    """Remote servers only (owner decision Q56): there is no local/stdio test."""

    url: str = Field(min_length=8, max_length=2048, pattern=r"^https://")
    token: str | None = Field(default=None, max_length=4096)


@router.post("/mcp/test")
async def dry_run_mcp(
    body: McpTest, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    server = McpConnector(HttpMcpTransport(body.url, body.token or None))
    try:
        # The listing handshake only (initialize, tools/list): no tool is called.
        await bounded(server.initialize())
        reviewed = review_tools(await bounded(server.tools()))
    finally:
        await server.close()
    return {
        "ok": True,
        "tools": sorted(reviewed.tools),
        "writes": reviewed.writes,
        "blocked": reviewed.blocked,
        "unsupported": reviewed.unsupported,
    }


class BrokerTest(BrokerConnection):
    api_key: str | None = Field(default=None, max_length=4096)


@router.post("/trading/connections/test")
async def dry_run_broker(
    request: Request, body: BrokerTest, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    config = BrokerConnection.model_validate(body.model_dump(exclude={"api_key"}))
    async with runtime(request).db.sessions() as session:
        # The same refusal a save would meet: this account is already linked.
        await BrokerSessionRepository().assert_unique(
            session, owner.id, config.model_dump(mode="json")
        )
    if config.provider != "simulation":
        # A MetaApi account is connected from chat (broker_connect, mandate 9.2).
        raise LonoraError("broker_connect_from_chat", 409)
    return {"ok": True, "provider": "simulation"}
