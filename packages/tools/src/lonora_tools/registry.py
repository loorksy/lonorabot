from typing import Any

from lonora_adapter_kit.types import ToolCall, ToolDefinition
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease

from .base import Tool
from .context import ToolContext
from .environment import EnvironmentInput
from .market_binding import guard_market_tool, prepare_market_arguments, scope_market_result
from .schema import validate_arguments


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise LonoraError("duplicate_tool_registration", 500)
        if any(tool.financial and tool.read_only for tool in tools):
            raise LonoraError("tool_effect_contract_invalid", 500)
        if "tool_environment" in self.tools:
            raise LonoraError("duplicate_tool_registration", 500)
        self.tools["tool_environment"] = Tool(
            "tool_environment",
            "Inspect actual available tool metadata and one exact input schema. Use after invalid arguments, missing capabilities or oversized results. Inspection grants no authority.",
            EnvironmentInput,
            self.inspect_environment,
            True,
        )

    async def inspect_environment(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        async with context.db.sessions() as session:
            run = await require_lease(session, context.lease)
            read_only = (
                run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
            )
        allowed = [tool for tool in self.tools.values() if not read_only or tool.read_only]
        name = arguments.get("tool_name")
        if name:
            tool = next((tool for tool in allowed if tool.name == name), None)
            if tool is None:
                raise LonoraError("tool_not_allowed", 403)
            return {"tool": tool.environment(), "execution_authorized": False}
        offset, limit = arguments["offset"], arguments["limit"]
        return {
            "tools": [tool.environment(schema=False) for tool in allowed[offset : offset + limit]],
            "total": len(allowed),
            "next_offset": offset + limit if offset + limit < len(allowed) else None,
            "execution_authorized": False,
        }

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
        arguments = await prepare_market_arguments(
            context, call.name, dict(call.arguments), tool.input_type
        )
        arguments = validate_arguments(tool.input_type, arguments)
        arguments = await guard_market_tool(context, call.name, arguments)
        result = await tool.handler(context.for_call(call.id), arguments)
        return await scope_market_result(context, call.name, result)
