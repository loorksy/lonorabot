import importlib
from typing import Any

from .base import Tool
from .registry import ToolRegistry

MODULES = (
    "agents",
    "message",
    "memory",
    "scratchpad",
    "routine",
    "search",
    "artifacts",
    "mcp",
    "subagent",
    "market",
    "market_watch",
    "trading_decision",
    "opportunity",
    "shadow",
    "chart",
    "chart_state",
    "chart_indicator",
    "chart_snapshot",
    "account",
    "trade",
    "trading_goal",
    "runtime_control",
    "tasks",
    "collaboration",
)


def load_tools() -> ToolRegistry:
    tools: list[Tool] = []
    for name in MODULES:
        module: Any = importlib.import_module("lonora_tools." + name)
        tools.extend(module.tools())
    return ToolRegistry(tools)
