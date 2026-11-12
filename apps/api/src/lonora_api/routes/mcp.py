from typing import Any

from lonora_contracts.mcp import McpConnection
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow
from lonora_db.transactions import ResourceRepository
from lonora_db.trusted_sources import revoke_server
from sqlalchemy.ext.asyncio import AsyncSession

from . import resource_router


class McpRepository(ResourceRepository):
    row_type = McpConnectionRow
    payload_model = McpConnection
    kind = "mcp"
    secret_scope = "integration"
    secret_scope_refusal = "mcp_credential_scope_forbidden"

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("transport") == "stdio" and payload.get("enabled"):
            raise LonoraError("mcp_stdio_isolation_required", 403)

    async def delete(self, session: AsyncSession, owner_id: str, resource_id: str) -> None:
        # Its trust goes with it: nothing would run, so nothing may still look trusted.
        await self.get(session, owner_id, resource_id, lock=True)
        await revoke_server(session, owner_id, resource_id)
        await super().delete(session, owner_id, resource_id)


router = resource_router("/mcp", McpRepository())
