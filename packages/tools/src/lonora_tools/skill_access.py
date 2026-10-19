"""Injected access to the Agent-owned instruction catalog, never a tool grant."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .context import ToolContext


class SkillAccess(Protocol):
    async def catalog(self, context: "ToolContext", offset: int, limit: int) -> dict[str, Any]: ...

    async def view(self, context: "ToolContext", skill_id: str) -> dict[str, Any]: ...
