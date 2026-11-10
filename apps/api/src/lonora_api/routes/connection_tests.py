"""«اختبار الاتصال»: dry-run checks before the owner saves a connection (WP-H).

Each route makes one real, read-only round trip with the values the form holds and stores
nothing: no secret, no catalog, no connection row. A model provider lists its models, an
MCP server is initialised and lists its tools (reviewed like the trust preview), a broker
account reports its identity. None of them grants or widens any authority.
"""

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
from lonora_trading.connections import verified_identity
from pydantic import Field

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.post("/providers/{provider}/test")
async def dry_run_provider(
    provider: ProviderId, body: ProviderCredential, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    adapter = model_adapter(provider, body.api_key)
    try:
        models = await adapter.discover()
    finally:
        await adapter.close()
    return {"ok": True, "models": [model.id for model in models][:200]}


class McpTest(Contract):
    """Remote servers only (owner decision Q56): there is no local/stdio test."""

    url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    token: str | None = Field(default=None, max_length=4096)


@router.post("/mcp/test")
async def dry_run_mcp(body: McpTest, owner: OwnerIdentity = Depends(require_owner)) -> dict[str, Any]:
    server = McpConnector(HttpMcpTransport(body.url, body.token or None))
    try:
        await server.initialize()
        reviewed = review_tools(await server.tools())
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
    if config.provider == "simulation":
        return {"ok": True, "provider": "simulation"}
    if not body.api_key:
        raise LonoraError("broker_secret_required", 409)
    identity = await verified_identity(config, body.api_key)
    return {
        "ok": True,
        "provider": config.provider,
        "identity": {
            key: identity.get(key)
            for key in ("login", "server", "broker", "name", "platform")
            if identity.get(key) is not None
        },
    }
