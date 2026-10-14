from dataclasses import dataclass
from pathlib import Path

from lonora_adapter_kit.secrets import SecretStore
from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_market.runtime import MarketRuntime
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.router import GlobalModelRouter
from lonora_tools.context import ToolContext
from lonora_trading.execution import ExecutionService


@dataclass
class OwnerServices:
    owner_id: str
    db: Database
    secrets: SecretStore
    brokers: BrokerManager
    router: GlobalModelRouter
    trading: ExecutionService
    market: MarketRuntime

    @classmethod
    def create(cls, db: Database, owner_id: str, key: str) -> "OwnerServices":
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
        return cls(owner_id, db, secrets, brokers, router, ExecutionService(db, brokers), market)

    def tool_context(
        self,
        agent_id: str,
        thread_id: str,
        lease: Lease,
        root: Path,
        depth: int = 0,
        maximum_subagents: int = 4,
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
        )

    async def close(self) -> None:
        await self.market.close()
        await self.brokers.close()
