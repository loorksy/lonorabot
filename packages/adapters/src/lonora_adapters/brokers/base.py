import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lonora_market.runtime import MarketRuntime

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_adapter_kit.secrets import SecretStore
from lonora_contracts.account import AccountState
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database


class BrokerManager:
    def __init__(self, db: Database, secrets: SecretStore):
        self.db, self.secrets = db, secrets
        self.market: MarketRuntime | None = None
        self.lock = asyncio.Lock()
        self.connections: dict[str, tuple[int, BrokerAdapter]] = {}

    async def get(self, owner_id: str, connection_id: str) -> BrokerAdapter:
        async with self.lock:
            return await self.connect(owner_id, connection_id)

    async def connect(self, owner_id: str, connection_id: str) -> BrokerAdapter:
        async with self.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, owner_id, connection_id)
            config = BrokerConnection.model_validate(row.payload)
            version = row.version
        if not config.enabled:
            raise LonoraError("broker_disabled", 409)
        previous = self.connections.get(connection_id)
        if previous and previous[0] == version:
            return previous[1]
        if previous:
            await previous[1].close()
        if config.provider == "simulation":
            from .simulation import SimulationBroker

            broker: BrokerAdapter = SimulationBroker(self.db, owner_id, connection_id)
        else:
            from .metaapi import MetaApiBroker

            if not config.secret_id:
                raise LonoraError("broker_secret_required", 409)
            broker = MetaApiBroker(
                config.account_id,
                config.region,
                await self.secrets.read(config.secret_id),
                connection_id,
            )
        self.connections[connection_id] = (version, broker)
        return broker

    async def account(self, owner_id: str, connection_id: str) -> AccountState:
        async with self.db.sessions() as session:
            saved = await BrokerSessionRepository().get(session, owner_id, connection_id)
            version = saved.version
        account = await (await self.get(owner_id, connection_id)).account()
        account.id = connection_id
        identity = {
            "broker": account.broker,
            "login": account.login,
            "server": account.server,
            "name": account.name,
            "platform": account.platform,
            "observed_at": account.observed_at.isoformat(),
            "connection_version": version,
        }
        async with self.db.sessions() as session, session.begin():
            saved = await BrokerSessionRepository().get(session, owner_id, connection_id, lock=True)
            if saved.version == version:
                saved.state = {**saved.state, "broker_identity": identity}
        return account

    async def close(self) -> None:
        for _, broker in self.connections.values():
            await broker.close()
        self.connections.clear()
