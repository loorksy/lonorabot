import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lonora_adapter_kit.secrets import SecretStore
from lonora_adapters.brokers.base import BrokerManager
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.workspace_given import GivenValues
from lonora_providers.router import GlobalModelRouter
from lonora_session.idempotency import stable_id
from lonora_trading.execution import ExecutionService
from lonora_workspace.client import WorkspaceClient

from .skill_access import SkillAccess

if TYPE_CHECKING:
    from .cli_token import CommandTokens


class RunDrain:
    """What a stopping Gateway tells the Runs it executes (docs/gateway-reliability.md).

    Once ``requested``, every Run hands back to the queue at its next step boundary, with
    its fence and checkpoint kept; a call already started runs to its end first.
    ``effects`` holds the workers inside a call that is not read-only, from
    ``before_effect`` until its result is checkpointed: the drain's backstop never cancels
    one of them there.
    """

    def __init__(self) -> None:
        self.requested = False
        self.effects: set[asyncio.Task[Any]] = set()

    def enter_effect(self) -> None:
        if task := asyncio.current_task():
            self.effects.add(task)

    def leave_effect(self) -> None:
        if task := asyncio.current_task():
            self.effects.discard(task)


@dataclass(frozen=True)
class ToolContext:
    db: Database
    owner_id: str
    agent_id: str
    thread_id: str
    lease: Lease
    brokers: BrokerManager
    trading: ExecutionService
    secrets: SecretStore
    router: GlobalModelRouter
    artifact_root: Path
    depth: int = 0
    maximum_subagents: int = 4
    call_id: str = ""
    chart_visual: ChartVisualRuntime | None = None
    skill_access: SkillAccess | None = None
    # The owner's persistent workspace (7.1), and the encrypted record of the secret
    # values given to its commands (kept in the scan after a rotation or a deletion).
    workspace: WorkspaceClient | None = None
    workspace_given: GivenValues | None = None
    # Each agent's `lonora` CLI token (7.3.3), set in the commands its full runs start.
    cli_tokens: "CommandTokens | None" = None
    mcp_declarations: tuple[McpToolDeclaration, ...] = ()
    mcp_owner_trust: bool = True
    searxng_url: str | None = None
    browser_url: str | None = None
    # The model this Run was started on (a subagent's chosen model); it leads the
    # Agent's own model chain, which stays behind it as the fallback.
    run_model: ModelSelection | None = None
    # The Gateway's drain signal; None outside a Gateway worker.
    drain: RunDrain | None = None

    @property
    def effect_key(self) -> str:
        return self.lease.run_id + ":" + self.call_id

    @property
    def resource_id(self) -> str:
        return stable_id(self.lease.run_id, self.call_id)

    def for_call(self, call_id: str) -> "ToolContext":
        return replace(self, call_id=call_id)
