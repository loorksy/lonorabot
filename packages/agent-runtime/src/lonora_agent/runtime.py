from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .executor import execute_run


class AgentRuntime:
    def __init__(self, tools: ToolRegistry, lease_seconds: int = 120, maximum_rounds: int = 24):
        self.tools, self.lease_seconds, self.maximum_rounds = tools, lease_seconds, maximum_rounds

    def read_only_names(self) -> set[str]:
        """Server-registry classification used when a Run's failure is recorded."""
        return {tool.name for tool in self.tools.tools.values() if tool.read_only}

    async def execute(self, context: ToolContext) -> None:
        await execute_run(context, self.tools, self.lease_seconds, self.maximum_rounds)
