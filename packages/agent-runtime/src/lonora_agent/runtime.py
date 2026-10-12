from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .executor import execute_run


class AgentRuntime:
    def __init__(self, tools: ToolRegistry, lease_seconds: int = 120, maximum_rounds: int = 24):
        self.tools, self.lease_seconds, self.maximum_rounds = tools, lease_seconds, maximum_rounds

    async def execute(self, context: ToolContext) -> None:
        await execute_run(context, self.tools, self.lease_seconds, self.maximum_rounds)
