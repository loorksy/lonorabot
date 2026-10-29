"""Read-only broker identity verification and atomic connection/credential creation."""

from typing import Any

from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import (
    BrokerSessionRepository,
    broker_identity_key,
    current_broker_identity,
)
from lonora_db.client import Database
from lonora_db.schema import BrokerSessionRow
from lonora_db.transactions import resource_data
from sqlalchemy import select


async def verified_identity(config: BrokerConnection, token: str) -> dict[str, Any]:
    broker = MetaApiBroker(config.account_id, config.region, token)
    try:
        identity = await broker.metadata_identity()
        if broker_identity_key(identity) is None:
            raise LonoraError("broker_identity_unavailable", 503)
        return {**identity, "observed_at": utcnow().isoformat()}
    finally:
        await broker.close()


async def connect_account(
    db: Database,
    secrets: EncryptedSecretStore,
    owner_id: str,
    config: BrokerConnection,
    api_key: str | None,
) -> dict[str, Any]:
    repository = BrokerSessionRepository()
    # A repeated click on an existing provider ID should not contact the provider
    # or replace the working credential with the newly submitted value.
    async with db.sessions() as session:
        await repository.assert_unique(session, owner_id, config.model_dump(mode="json"))
    identity: dict[str, Any] | None = None
    if config.provider == "metaapi":
        token = api_key or (await secrets.read(config.secret_id) if config.secret_id else None)
        if not token:
            raise LonoraError("broker_secret_required", 409)
        identity = await verified_identity(config, token)
    async with db.sessions() as session, session.begin():
        await repository.lock_owner(session, owner_id)
        await repository.assert_unique(
            session, owner_id, config.model_dump(mode="json"), identity=identity
        )
        if config.provider == "metaapi":
            # Backfill old connections from trusted provider metadata if no
            # current observed identity exists. Never trust caller identity fields.
            observations: list[tuple[str, int, BrokerConnection, dict[str, Any]]] = []
            for row in await repository.all_connections(session, owner_id):
                if row.payload.get("provider") != "metaapi":
                    continue
                saved = current_broker_identity(row)
                if saved is not None and broker_identity_key(saved):
                    continue
                existing = BrokerConnection.model_validate(row.payload)
                if not existing.secret_id:
                    raise LonoraError("broker_identity_unavailable", 503)
                version = row.version
                observed = await verified_identity(existing, await secrets.read(existing.secret_id))
                observations.append((row.id, version, existing, observed))
            # Finish ALL provider I/O before taking any broker row lock. Keeping
            # one earlier row locked while observing the next would stall recovery.
            for connection_id, version, existing, observed in observations:
                # Recovery observations do not acquire the owner lock. Refresh
                # under the broker row lock AFTER provider I/O so merging an
                # identity never overwrites a concurrently committed snapshot.
                refreshed = await session.scalar(
                    select(BrokerSessionRow)
                    .where(
                        BrokerSessionRow.id == connection_id, BrokerSessionRow.owner_id == owner_id
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if (
                    refreshed is None
                    or refreshed.version != version
                    or BrokerConnection.model_validate(refreshed.payload) != existing
                ):
                    raise LonoraError("broker_connection_changed", 409)
                refreshed.state = {
                    **refreshed.state,
                    "broker_identity": {**observed, "connection_version": refreshed.version},
                }
            await repository.assert_unique(
                session, owner_id, config.model_dump(mode="json"), identity=identity
            )
        if api_key:
            config.secret_id = await secrets.write_in_session(
                session, config.account_id, api_key, "broker"
            )
        row = await repository.create(
            session, owner_id, config.model_dump(mode="json"), broker_identity=identity
        )
        return resource_data(row)
