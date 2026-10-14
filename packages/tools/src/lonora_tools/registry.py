from typing import Any

from lonora_adapter_kit.types import ToolCall, ToolDefinition
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease

from .base import Tool
from .context import ToolContext
from .market_binding import guard_market_tool, scope_market_result
from .schema import validate_arguments


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise LonoraError("duplicate_tool_registration", 500)

    def definitions(self, read_only: bool = False) -> list[ToolDefinition]:
        return [
            tool.definition() for tool in self.tools.values() if not read_only or tool.read_only
        ]

    async def execute(
        self, call: ToolCall, context: ToolContext, read_only: bool = False
    ) -> dict[str, Any]:
        tool = self.tools.get(call.name)
        if tool is None or (read_only and not tool.read_only):
            raise LonoraError("tool_not_allowed", 403)
        async with context.db.sessions() as session:
            await require_lease(session, context.lease)
        arguments = validate_arguments(tool.input_type, call.arguments)
        arguments = await guard_market_tool(context, call.name, arguments)
        result = await tool.handler(context.for_call(call.id), arguments)
        return await scope_market_result(context, call.name, result)
