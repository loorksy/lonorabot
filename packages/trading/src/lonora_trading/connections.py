"""Read-only broker identity verification, and the simulation provider's connection."""

from typing import Any

from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.storage.broker_secrets import BrokerSecrets
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
from sqlalchemy.ext.asyncio import AsyncSession


async def verified_identity(config: BrokerConnection, token: str) -> dict[str, Any]:
    broker = MetaApiBroker(config.account_id, config.region, token)
    try:
        identity = await broker.metadata_identity()
        if broker_identity_key(identity) is None:
            raise LonoraError("broker_identity_unavailable", 503)
        return {**identity, "observed_at": utcnow().isoformat()}
    finally:
        await broker.close()


# A legacy connection MetaApi can no longer answer for (its account deleted, its token
# refused); a timeout or an outage is retried instead.
UNREADABLE = frozenset(
    {"broker_account_not_found", "broker_credentials_rejected", "broker_token_rejected"}
)


async def observe_legacy_identities(
    db: Database, secrets: BrokerSecrets, owner_id: str
) -> list[tuple[str, int, BrokerConnection, dict[str, Any]]]:
    """MetaApi's identity for every MetaApi connection with no current one (a legacy row,
    or one whose saved identity belongs to an older version), read before a new account
    is accepted: an alias of the same broker account is then caught by its identity.
    Provider I/O only; ``record_identities`` writes the results under the row locks."""
    repository = BrokerSessionRepository()
    async with db.sessions() as session:
        rows = await repository.all_connections(session, owner_id)
    observations: list[tuple[str, int, BrokerConnection, dict[str, Any]]] = []
    for row in rows:
        if row.payload.get("provider") != "metaapi":
            continue
        saved = current_broker_identity(row)
        if saved is not None and broker_identity_key(saved):
            continue
        existing = BrokerConnection.model_validate(row.payload)
        if not existing.secret_id:
            raise LonoraError("broker_identity_unavailable", 503)
        try:
            observed = await verified_identity(existing, await secrets.read(existing.secret_id))
        except LonoraError as failure:
            if failure.code in UNREADABLE:
                # Its account is gone at MetaApi or its token is refused: whether a new
                # account is the same broker account cannot be told. The owner removes the
                # old connection (broker_manage disconnect) and connects again.
                raise LonoraError("broker_legacy_connection_unreadable", 409) from None
            raise
        observations.append((row.id, row.version, existing, observed))
    return observations


async def record_identities(
    session: AsyncSession,
    owner_id: str,
    observations: list[tuple[str, int, BrokerConnection, dict[str, Any]]],
) -> None:
    """Writes ``observe_legacy_identities``'s results, after all provider I/O. Recovery
    observations do not take the owner lock: each row is refreshed under its own lock so
    merging an identity never overwrites a concurrently committed snapshot."""
    for connection_id, version, existing, observed in observations:
        refreshed = await session.scalar(
            select(BrokerSessionRow)
            .where(BrokerSessionRow.id == connection_id, BrokerSessionRow.owner_id == owner_id)
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


async def connect_account(db: Database, owner_id: str, config: BrokerConnection) -> dict[str, Any]:
    """A simulation (demo) connection; it has no credential. A MetaApi account is connected
    from chat (``broker_connect``, mandate 9.2): Lonora provisions it, nobody types its id."""
    if config.provider != "simulation":
        raise LonoraError("broker_connect_from_chat", 409)
    repository = BrokerSessionRepository()
    async with db.sessions() as session, session.begin():
        await repository.lock_owner(session, owner_id)
        row = await repository.create(
            session, owner_id, config.model_copy(update={"secret_id": None}).model_dump(mode="json")
        )
        return resource_data(row)
