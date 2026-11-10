import importlib
from dataclasses import replace
from typing import Any

from .base import Tool
from .registry import ToolRegistry

# Each module's default toolset: the capability family and the operating-policy
# chapter that governs its tools. A Tool may declare its own toolset instead.
MODULES = {
    "agents": "collaboration",
    "message": "collaboration",
    "memory": "memory",
    "session_search": "memory",
    "scratchpad": "memory",
    "skills": "memory",
    "workspace": "files",
    "routine": "tasks",
    "search": "research",
    "browser": "research",
    "artifacts": "files",
    "mcp": "research",
    "feeds": "research",
    "capabilities": "research",
    "subagent": "collaboration",
    "market": "market",
    "market_analysis": "market",
    "position_sizing": "trading",
    "market_watch": "market",
    "trading_decision": "intelligence",
    "relationships": "intelligence",
    "opportunity": "intelligence",
    "consult": "intelligence",
    "models": "intelligence",
    "performance": "intelligence",
    "chart": "charts",
    "chart_state": "charts",
    "chart_indicator": "charts",
    "chart_snapshot": "charts",
    "account": "account",
    "trade": "trading",
    "restrictions": "trading",
    "owner_actions": "trading",
    "trading_goal": "goals",
    "runtime_control": "tasks",
    "tasks": "tasks",
    "collaboration": "collaboration",
    "supervision": "collaboration",
    "incoming_call": "voice",
}


def load_tools() -> ToolRegistry:
    tools: list[Tool] = []
    for name, toolset in MODULES.items():
        module: Any = importlib.import_module("lonora_tools." + name)
        tools.extend(
            tool if tool.toolset else replace(tool, toolset=toolset) for tool in module.tools()
        )
    return ToolRegistry(tools)
