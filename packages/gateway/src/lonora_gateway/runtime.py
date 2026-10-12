from dataclasses import dataclass
from pathlib import Path

from lonora_adapter_kit.secrets import SecretStore
from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_contracts.runs import Lease
from lonora_db.client import Database
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

    @classmethod
    def create(cls, db: Database, owner_id: str, key: str) -> "OwnerServices":
        secrets = EncryptedSecretStore(db, key, owner_id)
        brokers = BrokerManager(db, secrets)
        router = GlobalModelRouter(db, ProviderCredentials(db, secrets))
        return cls(owner_id, db, secrets, brokers, router, ExecutionService(db, brokers))

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
        await self.brokers.close()
