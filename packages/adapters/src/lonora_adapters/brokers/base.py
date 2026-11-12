import asyncio
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lonora_market.runtime import MarketRuntime

    from ..storage.broker_secrets import BrokerSecrets

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.account import AccountState
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.events import emit


class BrokerManager:
    def __init__(self, db: Database, secrets: "BrokerSecrets"):
        # The broker destination (7.2.3): only this layer and provisioning read it.
        self.db, self._secrets = db, secrets
        self.market: MarketRuntime | None = None
        self.lock = asyncio.Lock()
        self.closed = False
        self.connections: dict[str, tuple[int, BrokerAdapter]] = {}

    async def get(self, owner_id: str, connection_id: str) -> BrokerAdapter:
        async with self.lock:
            if self.closed:
                raise LonoraError("broker_connection_unavailable", 503)
            return await self.connect(owner_id, connection_id)

    async def connect(self, owner_id: str, connection_id: str) -> BrokerAdapter:
        async with self.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, owner_id, connection_id)
            config = BrokerConnection.model_validate(row.payload)
            version = row.version
        if not config.enabled:
            raise LonoraError("broker_disabled", 409)
        previous = self.connections.get(connection_id)
        if previous and previous[0] == version and not getattr(previous[1], "closed", False):
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
                await self._secrets.read(config.secret_id),
                connection_id,
            )
        self.connections[connection_id] = (version, broker)
        return broker

    async def provisioning(self, owner_id: str, connection_id: str) -> Any:
        """A MetaApi provisioning client on this connection's token (account-entity calls
        only). The token stays in the broker layer; the caller gets the client."""
        from .metaapi_provisioning import MetaApiProvisioning

        async with self.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, owner_id, connection_id)
            config = BrokerConnection.model_validate(row.payload)
        if config.provider != "metaapi" or not config.secret_id:
            raise LonoraError("broker_not_metaapi", 409)
        factory = getattr(self, "provisioning_factory", MetaApiProvisioning)
        return factory(await self._secrets.read(config.secret_id))

    async def forget_secret(self, owner_id: str, secret_id: str) -> None:
        """Delete a broker value no connection uses any more (disconnect's password or a
        per-account token copy). Nothing is read; the broker layer does the deleting."""
        del owner_id  # The reader is already the owner's.
        await self._secrets.delete_unused(secret_id)

    async def account(self, owner_id: str, connection_id: str) -> AccountState:
        async with self.db.sessions() as session:
            saved = await BrokerSessionRepository().get(session, owner_id, connection_id)
            version = saved.version
        broker = await self.get(owner_id, connection_id)
        account = await broker.account()
        account.id = connection_id
        # A connection linked without its region (an older link) records the region MetaApi
        # reports, so its next adapter asks the account's own region, not the SDK default.
        region = getattr(broker, "region", None)
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
            if saved.version != version:
                raise LonoraError("broker_connection_changed", 409)
            previous = saved.state.get("broker_identity", {})
            previous_identity = cast(dict[str, Any], previous) if isinstance(previous, dict) else {}
            semantic = {key: value for key, value in identity.items() if key != "observed_at"}
            changed = any(previous_identity.get(key) != value for key, value in semantic.items())
            saved.state = {**saved.state, "broker_identity": identity}
            if (
                isinstance(region, str)
                and saved.payload.get("provider") == "metaapi"
                and not saved.payload.get("region")
            ):
                # Not a credential or identity change: the version and the adapter stay.
                saved.payload = {**saved.payload, "region": region}
            if changed:
                emit(
                    session,
                    owner_id,
                    "broker_identity.updated",
                    payload={"connection_id": connection_id, "broker_identity": identity},
                )
        return account

    async def close(self) -> None:
        async with self.lock:
            if self.closed:
                return
            self.closed = True
            connections = list(self.connections.values())
            self.connections.clear()
            results = await asyncio.gather(
                *(broker.close() for _, broker in connections), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
