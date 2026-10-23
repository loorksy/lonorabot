import asyncio
from typing import Any, cast

from lonora_core.user_error import LonoraError

from .policy import schema_sha256
from .transport import McpTransport

MAX_DISCOVERED_TOOLS = 200
PROTOCOL_TIMEOUT_SECONDS = 30


class McpConnector:
    def __init__(self, transport: McpTransport):
        self.transport = transport
        self.sequence = 0

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        response = await self.transport.request(
            {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}
        )
        if (
            response.get("jsonrpc") != "2.0"
            or type(response.get("id")) is not int
            or response["id"] != self.sequence
            or ("result" in response) == ("error" in response)
        ):
            raise LonoraError("mcp_response_invalid", 502)
        if "error" in response:
            # Remote messages/data can contain credentials or instructions.
            raise LonoraError("mcp_protocol_error", 502)
        result = response["result"]
        if not isinstance(result, dict):
            raise LonoraError("mcp_response_invalid", 502)
        return cast(dict[str, Any], result)

    async def initialize(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(PROTOCOL_TIMEOUT_SECONDS):
                result = await self.call(
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "Lonora", "version": "0.2.0"},
                    },
                )
                if result.get("protocolVersion") != "2025-06-18":
                    raise LonoraError("mcp_protocol_unsupported", 502)
                await self.transport.request(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                )
                return result
        except TimeoutError:
            raise LonoraError("mcp_connection_timeout", 504) from None

    async def tools(self) -> list[dict[str, Any]]:
        try:
            async with asyncio.timeout(PROTOCOL_TIMEOUT_SECONDS):
                return await self._tools()
        except TimeoutError:
            raise LonoraError("mcp_connection_timeout", 504) from None

    async def _tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        names: set[str] = set()
        cursors: set[str] = set()
        cursor: str | None = None
        for _ in range(10):
            result = await self.call("tools/list", {"cursor": cursor} if cursor else {})
            page = result.get("tools")
            if not isinstance(page, list):
                raise LonoraError("mcp_tools_invalid", 502)
            values = cast(list[Any], page)
            if len(values) + len(tools) > MAX_DISCOVERED_TOOLS:
                raise LonoraError("mcp_tools_invalid", 502)
            for value in values:
                if not isinstance(value, dict):
                    raise LonoraError("mcp_tools_invalid", 502)
                item = cast(dict[str, Any], value)
                name, schema = item.get("name"), item.get("inputSchema")
                if (
                    not isinstance(name, str)
                    or not name
                    or len(name) > 128
                    or name in names
                    or not isinstance(schema, dict)
                ):
                    raise LonoraError("mcp_tools_invalid", 502)
                schema_sha256(cast(dict[str, Any], schema))
                for key, limit in (("title", 128), ("description", 4000)):
                    text = item.get(key)
                    if text is not None and (not isinstance(text, str) or len(text) > limit):
                        raise LonoraError("mcp_tools_invalid", 502)
                names.add(name)
                tools.append(item)
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                return tools
            if (
                not isinstance(next_cursor, str)
                or not next_cursor
                or len(next_cursor) > 1000
                or next_cursor in cursors
            ):
                raise LonoraError("mcp_tools_invalid", 502)
            cursors.add(next_cursor)
            cursor = next_cursor
        raise LonoraError("mcp_tools_limit_exceeded", 502)

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        # Transport failures are not resent. Runtime recovery retains existing
        # non-read-only mcp_execute semantics and at-most-once receipts.
        result = await self.call("tools/call", {"name": name, "arguments": args})
        if "isError" in result and type(result["isError"]) is not bool:
            raise LonoraError("mcp_response_invalid", 502)
        if result.get("isError"):
            raise LonoraError("mcp_tool_failed", 502)
        if not isinstance(result.get("content"), list):
            raise LonoraError("mcp_response_invalid", 502)
        return result

    async def close(self) -> None:
        await self.transport.close()
