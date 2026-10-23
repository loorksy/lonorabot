"""Injected access to the Agent-owned instruction catalog, never a tool grant."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .context import ToolContext


class SkillAccess(Protocol):
    async def import_package(
        self, context: "ToolContext", arguments: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def validate_package(
        self, context: "ToolContext", arguments: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def control_package(
        self, context: "ToolContext", arguments: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def catalog(self, context: "ToolContext", offset: int, limit: int) -> dict[str, Any]: ...

    async def view(self, context: "ToolContext", skill_id: str) -> dict[str, Any]: ...

    async def inspect_repository(
        self, context: "ToolContext", repository_url: str, ref: str
    ) -> dict[str, Any]: ...
