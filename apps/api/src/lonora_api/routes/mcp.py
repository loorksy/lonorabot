from typing import Any

from lonora_contracts.mcp import McpConnection
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow, SecretRow
from lonora_db.transactions import ResourceRepository
from sqlalchemy.ext.asyncio import AsyncSession

from . import resource_router


class McpRepository(ResourceRepository):
    row_type = McpConnectionRow
    payload_model = McpConnection
    kind = "mcp"

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("transport") == "stdio" and payload.get("enabled"):
            raise LonoraError("mcp_stdio_isolation_required", 403)
        secret_id = payload.get("secret_id")
        if secret_id:
            secret = await session.get(SecretRow, secret_id)
            if secret is None or secret.owner_id != owner_id or secret.scope != "integration":
                raise LonoraError("mcp_credential_scope_forbidden", 403)


router = resource_router("/mcp", McpRepository())
