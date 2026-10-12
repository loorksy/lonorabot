from typing import Any

from lonora_core.user_error import LonoraError

from .transport import McpTransport


class McpConnector:
    def __init__(self, transport: McpTransport):
        self.transport = transport
        self.sequence = 0

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        response = await self.transport.request(
            {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}
        )
        if "error" in response:
            raise LonoraError("mcp_tool_failed", 502)
        return response.get("result", {})

    async def initialize(self) -> dict[str, Any]:
        result = await self.call(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "Lonora", "version": "0.2.0"},
            },
        )
        await self.transport.request({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    async def tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(10):
            result = await self.call("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self.call("tools/call", {"name": name, "arguments": args})

    async def close(self) -> None:
        await self.transport.close()
