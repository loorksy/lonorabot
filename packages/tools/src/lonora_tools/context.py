from dataclasses import dataclass, replace
from pathlib import Path

from lonora_adapter_kit.secrets import SecretStore
from lonora_adapters.brokers.base import BrokerManager
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_providers.router import GlobalModelRouter
from lonora_session.idempotency import stable_id
from lonora_trading.execution import ExecutionService

from .skill_access import SkillAccess
from .workspace_access import WorkspaceAccess


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
    workspace_access: WorkspaceAccess | None = None
    mcp_declarations: tuple[McpToolDeclaration, ...] = ()

    @property
    def effect_key(self) -> str:
        return self.lease.run_id + ":" + self.call_id

    @property
    def resource_id(self) -> str:
        return stable_id(self.lease.run_id, self.call_id)

    def for_call(self, call_id: str) -> "ToolContext":
        return replace(self, call_id=call_id)
