from dataclasses import dataclass
from pathlib import Path

from lonora_adapter_kit.secrets import SecretStore
from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_agent.workspace_client import WorkspaceClient
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.workspace_given import GivenValues
from lonora_market.runtime import MarketRuntime
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.router import GlobalModelRouter
from lonora_tools.cli_token import CommandTokens
from lonora_tools.context import ToolContext
from lonora_trading.execution import ExecutionService
from lonora_workspace.client import WorkspaceClient as Workspace

# The owner's workspace is part of every installation (docker-compose.prod.yml): its
# supervisor's socket is mounted into the Gateway at the client's default path.
WORKSPACE = Workspace()


@dataclass
class OwnerServices:
    owner_id: str
    db: Database
    secrets: SecretStore
    brokers: BrokerManager
    router: GlobalModelRouter
    trading: ExecutionService
    market: MarketRuntime
    chart_visual: ChartVisualRuntime | None = None
    workspace_socket: Path | None = None
    mcp_declarations: tuple[McpToolDeclaration, ...] = ()
    searxng_url: str | None = None
    browser_url: str | None = None
    mcp_owner_trust: bool = True
    given: GivenValues | None = None
    cli_tokens: CommandTokens | None = None

    @classmethod
    def create(
        cls,
        db: Database,
        owner_id: str,
        key: str,
        *,
        chart_visual: ChartVisualRuntime | None = None,
        workspace_socket: Path | None = None,
        mcp_declarations: tuple[McpToolDeclaration, ...] = (),
        searxng_url: str | None = None,
        browser_url: str | None = None,
        mcp_owner_trust: bool = True,
    ) -> "OwnerServices":
        secrets = EncryptedSecretStore(db, key, owner_id)
        brokers = BrokerManager(db, secrets)
        router = GlobalModelRouter(db, ProviderCredentials(db, secrets))
        market = MarketRuntime(db, brokers, owner_id)

        async def publish_market_update(
            connection_id: str, symbol: str, timeframe: str | None, stream_identity: str
        ) -> None:
            from lonora_charts.runtime import publish_stream_update

            await publish_stream_update(
                db, owner_id, connection_id, symbol, timeframe, stream_identity
            )

        market.on_update = publish_market_update
        brokers.market = market
        return cls(
            owner_id,
            db,
            secrets,
            brokers,
            router,
            ExecutionService(db, brokers),
            market,
            chart_visual,
            workspace_socket,
            mcp_declarations,
            searxng_url,
            browser_url,
            mcp_owner_trust,
            GivenValues(db, key, owner_id),
            CommandTokens(db, key, owner_id),
        )

    def tool_context(
        self,
        agent_id: str,
        thread_id: str,
        lease: Lease,
        root: Path,
        depth: int = 0,
        maximum_subagents: int = 4,
        run_model: ModelSelection | None = None,
    ) -> ToolContext:
        return ToolContext(
            self.db,
            self.owner_id,
            agent_id,
            thread_id,
            lease,
            self.brokers,
            self.trading,
            self.secrets,
            self.router,
            root,
            depth,
            maximum_subagents,
            chart_visual=self.chart_visual,
            workspace_access=RunWorkspaceAccess(
                WorkspaceClient(self.workspace_socket) if self.workspace_socket else None
            ),
            workspace=WORKSPACE,
            workspace_given=self.given,
            cli_tokens=self.cli_tokens,
            mcp_declarations=self.mcp_declarations,
            mcp_owner_trust=self.mcp_owner_trust,
            searxng_url=self.searxng_url,
            browser_url=self.browser_url,
            run_model=run_model,
        )

    async def close(self) -> None:
        try:
            if self.chart_visual:
                await self.chart_visual.close()
        finally:
            try:
                await self.market.close()
            finally:
                await self.brokers.close()
