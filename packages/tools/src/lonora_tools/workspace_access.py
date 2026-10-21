"""Injected, fenced access to analytical files; never a financial authority."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .context import ToolContext


class WorkspaceAccess(Protocol):
    async def inspect(self, context: "ToolContext") -> dict[str, Any]: ...
    async def read(
        self, context: "ToolContext", path: str, revision: int, offset: int, limit: int
    ) -> dict[str, Any]: ...
    async def update(
        self, context: "ToolContext", revision: int, files: dict[str, str], delete: list[str]
    ) -> dict[str, Any]: ...
    async def execute(
        self, context: "ToolContext", revision: int, command: str, deadline_seconds: int
    ) -> dict[str, Any]: ...
