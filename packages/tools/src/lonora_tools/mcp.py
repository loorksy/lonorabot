from typing import Any

from lonora_adapters.mcp.connector import McpConnector
from lonora_adapters.mcp.transport import HttpMcpTransport, StdioMcpTransport
from lonora_contracts.domain import Contract
from lonora_contracts.mcp import McpConnection
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow
from pydantic import Field

from .base import Tool
from .context import ToolContext


class McpRead(Contract):
    connection_id: str


class McpExecute(McpRead):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])


async def connector(context: ToolContext, connection_id: str) -> McpConnector:
    async with context.db.sessions() as session:
        row = await session.get(McpConnectionRow, connection_id)
        if row is None or row.owner_id != context.owner_id:
            raise LonoraError("mcp_not_found", 404)
        config = McpConnection.model_validate(row.payload)
    if not config.enabled:
        raise LonoraError("mcp_disabled", 409)
    token = await context.secrets.read(config.secret_id) if config.secret_id else None
    transport = (
        HttpMcpTransport(config.url or "", token)
        if config.transport == "http"
        else StdioMcpTransport(config.command)
    )
    result = McpConnector(transport)
    await result.initialize()
    return result


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    adapter = await connector(context, args["connection_id"])
    try:
        return {"tools": await adapter.tools()}
    finally:
        await adapter.close()


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    adapter = await connector(context, args["connection_id"])
    try:
        advertised = {item["name"] for item in await adapter.tools()}
        if args["name"] not in advertised:
            raise LonoraError("mcp_tool_not_found", 404)
        return await adapter.execute(args["name"], args["arguments"])
    finally:
        await adapter.close()


def tools() -> list[Tool]:
    return [
        Tool(
            "mcp_tools",
            "Inspect tools advertised by an enabled owner-configured MCP connection.",
            McpRead,
            read,
            True,
        ),
        Tool(
            "mcp_execute",
            "Execute a tool on an enabled connection. Credentials remain on the server.",
            McpExecute,
            execute,
        ),
    ]
