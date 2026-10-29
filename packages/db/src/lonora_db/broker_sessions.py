from typing import Any, cast

from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import BrokerSessionRow, OwnerRow, ResourceRow
from .transactions import ResourceRepository


def broker_identity_key(identity: dict[str, Any]) -> tuple[str, str, str] | None:
    """Only a broker-observed login/server/platform identifies an actual account."""
    values = tuple(
        str(identity.get(key) or "").strip().casefold() for key in ("login", "server", "platform")
    )
    if not all(values):
        return None
    login, server, platform = values
    if login.isascii() and login.isdigit():
        login = str(int(login))
    return login, server, platform


def current_broker_identity(row: ResourceRow) -> dict[str, Any] | None:
    value = row.state.get("broker_identity")
    if not isinstance(value, dict):
        return None
    identity = cast(dict[str, Any], value)
    return identity if identity.get("connection_version") == row.version else None


class BrokerSessionRepository(ResourceRepository):
    """One owner connection per provider ID and per verified broker identity."""

    row_type = BrokerSessionRow
    kind = "broker_sessions"
    payload_model = BrokerConnection

    async def lock_owner(self, session: AsyncSession, owner_id: str) -> None:
        # An existing owner row serializes even the first connection across API
        # workers. Keep the lock until the caller's transaction commits.
        owner = await session.scalar(
            select(OwnerRow.id).where(OwnerRow.id == owner_id).with_for_update()
        )
        if owner is None:
            raise LonoraError("owner_not_found", 404)

    async def all_connections(self, session: AsyncSession, owner_id: str) -> list[BrokerSessionRow]:
        # Identity validation must not inherit the UI directory's 200-row limit.
        return list(
            await session.scalars(
                select(BrokerSessionRow).where(BrokerSessionRow.owner_id == owner_id)
            )
        )

    async def assert_unique(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        identity: dict[str, Any] | None = None,
        exclude_id: str | None = None,
    ) -> None:
        config = BrokerConnection.model_validate(payload)
        key = broker_identity_key(identity or {})
        for row in await self.all_connections(session, owner_id):
            if row.id == exclude_id:
                continue
            if row.payload.get("provider") != config.provider:
                continue
            same_provider_id = (
                str(row.payload.get("account_id", "")).strip() == config.account_id.strip()
            )
            saved = current_broker_identity(row)
            same_broker = (
                key is not None and saved is not None and broker_identity_key(saved) == key
            )
            if same_provider_id or same_broker:
                raise LonoraError("broker_account_already_connected", 409)

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
        broker_identity: dict[str, Any] | None = None,
    ) -> BrokerSessionRow:
        await self.lock_owner(session, owner_id)
        config = BrokerConnection.model_validate(payload)
        await self.assert_unique(session, owner_id, payload, identity=broker_identity)
        if config.provider == "metaapi" and broker_identity_key(broker_identity or {}) is None:
            raise LonoraError("broker_identity_unavailable", 503)
        row = await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )
        if broker_identity:
            row.state = {
                **row.state,
                "broker_identity": {**broker_identity, "connection_version": row.version},
            }
        # ResourceRepository constructs this concrete row_type.
        assert isinstance(row, BrokerSessionRow)
        return row

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> BrokerSessionRow:
        await self.lock_owner(session, owner_id)
        row = await self.get(session, owner_id, resource_id, lock=True)
        config = BrokerConnection.model_validate(payload)
        previous = BrokerConnection.model_validate(row.payload)
        identity = current_broker_identity(row)
        verified = identity is not None
        same_credentials = all(
            getattr(config, key) == getattr(previous, key)
            for key in ("provider", "account_id", "region", "secret_id")
        )
        if config.provider == "metaapi" and not (verified and same_credentials):
            raise LonoraError("broker_identity_unavailable", 503)
        await self.assert_unique(
            session,
            owner_id,
            payload,
            identity=identity if verified else None,
            exclude_id=resource_id,
        )
        updated = await super().update(session, owner_id, resource_id, payload, version)
        if identity is not None and same_credentials:
            updated.state = {
                **updated.state,
                "broker_identity": {**identity, "connection_version": updated.version},
            }
        assert isinstance(updated, BrokerSessionRow)
        return updated
