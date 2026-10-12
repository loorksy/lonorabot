from typing import Any

from lonora_adapter_kit.types import ToolDefinition


def bridge_tools(connection_id: str, tools: list[dict[str, Any]]) -> list[ToolDefinition]:
    # Namespaces remain stable without giving the model transport credentials.
    return [
        ToolDefinition(
            name="mcp_" + connection_id.replace("-", "")[:8] + "_" + item["name"],
            description=item.get("description", item["name"]),
            parameters=item.get("inputSchema", {"type": "object", "properties": {}}),
        )
        for item in tools
    ]
