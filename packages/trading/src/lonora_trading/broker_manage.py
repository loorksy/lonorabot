"""Manage the owner's broker connections from chat (VISION.md 9.3).

Enable and disable flip the stored switch; disconnect removes the connection. Every
change runs under the account's send lock (the lock the door holds from its send
boundary to an outcome), so it waits for a send in flight and the next send sees the new
version. While an operation on the account has no confirmed outcome, disable, disconnect
and any undeploy or removal at MetaApi are refused (R3): reconciliation needs the account.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.obligations import prepare_delete, unsettled_obligation
from lonora_db.schema import SecretRow
from lonora_db.secrets import METAAPI_TOKEN
from sqlalchemy import select, text

from . import broker_provisioning
from .reconciliation import send_lock_key

# MetaApi calls made while the account's send lock is held end within this, so an exit
# waiting at the door is never held up for long by a slow MetaApi.
METAAPI_SECONDS = 120


@asynccontextmanager
async def send_locked(db: Database, owner_id: str, connection_id: str) -> AsyncGenerator[None]:
    """Hold the account's send lock: a send in flight finishes first, none starts."""
    async with db.sessions() as gate, gate.begin():
        await gate.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": send_lock_key(owner_id, connection_id)},
        )
        yield


async def refuse_unsettled(db: Database, owner_id: str, connection_id: str) -> None:
    async with db.sessions() as session:
        if await unsettled_obligation(session, owner_id, account_id=connection_id):
            raise LonoraError("broker_operation_unsettled", 409)


async def set_enabled(
    db: Database, brokers: Any, owner_id: str, connection_id: str, enabled: bool
) -> dict[str, Any]:
    if not enabled:
        await refuse_unsettled(db, owner_id, connection_id)
    repository = BrokerSessionRepository()
    async with send_locked(db, owner_id, connection_id):
        async with db.sessions() as session, session.begin():
            # Again under the send lock: a send that won the lock may have ended uncertain.
            if not enabled and await unsettled_obligation(
                session, owner_id, account_id=connection_id
            ):
                raise LonoraError("broker_operation_unsettled", 409)
            row = await repository.get(session, owner_id, connection_id)
            payload = BrokerConnection.model_validate(row.payload)
            if payload.enabled != enabled:
                payload.enabled = enabled
                await repository.update(
                    session, owner_id, connection_id, payload.model_dump(mode="json"), row.version
                )
    # The version moved: BrokerManager replaces its cached adapter on the next use.
    result: dict[str, Any] = {"connection_id": connection_id, "enabled": enabled}
    if not enabled:
        # Q9: said, not hidden: nothing on this account is read or managed while off.
        result["note"] = (
            "Disabled: its open positions and orders stay at the broker and are not read "
            "or managed by any agent until it is enabled again."
        )
    return result


async def disconnect(
    db: Database, brokers: Any, owner_id: str, connection_id: str
) -> dict[str, Any]:
    """Remove the connection. A MetaApi account Lonora created is undeployed and removed
    there too; one the owner linked by id is left as it is. The trading password is
    deleted; the owner's MetaApi token is kept for other accounts (Q8). No value is read
    here."""
    await refuse_unsettled(db, owner_id, connection_id)
    repository = BrokerSessionRepository()
    async with db.sessions() as session:
        row = await repository.get(session, owner_id, connection_id)
        payload = BrokerConnection.model_validate(row.payload)
        state = dict(row.state)
        token = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == owner_id,
                SecretRow.scope == "broker",
                SecretRow.name == METAAPI_TOKEN,
            )
        )
    left = await _open_at_broker(brokers, owner_id, connection_id)
    remove = payload.provider == "metaapi" and state.get("provisioned_by_lonora") is True
    provisioning = await brokers.provisioning(owner_id, connection_id) if remove else None
    removed: bool | str = False
    try:
        async with send_locked(db, owner_id, connection_id):
            # prepare_delete first (Q8): refused while an operation is uncertain, and only
            # then is anything removed, so broker truth stays until nothing needs it.
            async with db.sessions() as session, session.begin():
                await prepare_delete(session, owner_id, account_id=connection_id)
                await repository.delete(session, owner_id, connection_id)
        if provisioning is not None:
            try:
                async with asyncio.timeout(METAAPI_SECONDS):
                    await provisioning.undeploy(payload.account_id)
                    await provisioning.remove(payload.account_id)
                removed = True
            except (LonoraError, TimeoutError) as failure:
                # The connection is gone; only MetaApi's copy is left (it keeps billing).
                code = getattr(failure, "code", "broker_provisioning_timeout")
                removed = True if code == "broker_account_not_found" else code
    finally:
        if provisioning is not None:
            await provisioning.close()
    await _close_adapter(brokers, connection_id)
    password = state.get("password_secret_id")
    for secret_id in (password, payload.secret_id if payload.secret_id != token else None):
        if isinstance(secret_id, str):
            # The broker layer forgets it (under the provisioning lock) unless still used.
            await brokers.forget_secret(owner_id, secret_id)
    result: dict[str, Any] = {
        "connection_id": connection_id,
        "removed_at_metaapi": removed is True,
        # Said, not hidden: what the broker still holds is no longer read or managed.
        "note": "Disconnected: its open positions and orders stay at the broker and are no "
        "longer read or managed by any agent.",
        **left,
    }
    if isinstance(removed, str):
        result["metaapi_not_removed"] = removed
    return result


async def _open_at_broker(brokers: Any, owner_id: str, connection_id: str) -> dict[str, Any]:
    """How many positions and orders the broker holds, read just before disconnecting."""
    try:
        async with asyncio.timeout(20):
            broker = await brokers.get(owner_id, connection_id)
            return {
                "open_positions": len(await broker.positions()),
                "pending_orders": len(await broker.orders()),
            }
    except Exception:  # noqa: BLE001 - a count is information; disconnect goes on
        return {"open_positions": "unknown", "pending_orders": "unknown"}


async def _close_adapter(brokers: Any, connection_id: str) -> None:
    """The connection row is gone: close its cached adapter, under the manager's lock."""
    async with brokers.lock:
        prior = brokers.connections.pop(connection_id, None)
    if prior:
        await prior[1].close()


async def rotate_password(
    db: Database, brokers: Any, secrets: BrokerSecrets, owner_id: str, card: Any
) -> str | None:
    """Store the owner's new password at MetaApi and redeploy with it (Q7). Returns a
    failure code, or None when done. The connection's version moves under the send lock,
    so no send uses a connection object from before the change."""
    from lonora_db.secrets import metaapi_password_name

    del brokers  # The version moved: BrokerManager replaces its cached adapter itself.
    connection_id = str(card.payload["connection_id"])
    new_password = await secrets.named(metaapi_password_name(card.id))
    if new_password is None:
        return "broker_secret_required"
    stored = sent = False
    old_password: Any = None
    try:
        repository = BrokerSessionRepository()
        async with db.sessions() as session:
            row = await repository.get(session, owner_id, connection_id)
            payload = BrokerConnection.model_validate(row.payload)
            old_password = row.state.get("password_secret_id")
        if payload.provider != "metaapi" or not payload.secret_id:
            return "broker_not_metaapi"
        provisioning = broker_provisioning.provisioning_client(
            await secrets.read(payload.secret_id)
        )
        try:
            async with send_locked(db, owner_id, connection_id):
                # Under the send lock: a send that won the lock may have ended uncertain.
                await refuse_unsettled(db, owner_id, connection_id)
                async with asyncio.timeout(METAAPI_SECONDS):
                    await provisioning.update_password(
                        payload.account_id, await secrets.read(new_password)
                    )
                sent = True
                # MetaApi holds the new password now: record it and move the version at once.
                async with db.sessions() as session, session.begin():
                    await repository.credentials_changed(
                        session,
                        owner_id,
                        connection_id,
                        state={"password_secret_id": new_password},
                    )
                stored = True
                async with asyncio.timeout(METAAPI_SECONDS):
                    await provisioning.redeploy(payload.account_id)
        finally:
            await provisioning.close()
    except (LonoraError, TimeoutError) as failure:
        if sent and not stored:
            return "broker_rotation_incomplete"  # MetaApi may hold it; nothing recorded
        if not stored:
            return getattr(failure, "code", "broker_provisioning_timeout")
        # Stored and recorded, but the terminal was not redeployed with it yet.
        partial: str | None = "broker_redeploy_failed"
    else:
        partial = None
    if isinstance(old_password, str) and old_password != new_password:
        await secrets.delete_unused(old_password)
    return partial


async def replace_token(
    db: Database, brokers: Any, secrets: BrokerSecrets, owner_id: str, card: Any
) -> str | None:
    """Make the owner's new MetaApi token the one every MetaApi connection names. It must
    see every connected account first; otherwise nothing changes (a token of another
    MetaApi user would cut every account off)."""
    pending = await secrets.named("metaapi_token_next:" + card.id)
    if pending is None:
        return "broker_secret_required"
    token = await secrets.read(pending)
    repository = BrokerSessionRepository()
    async with db.sessions() as session:
        rows = [
            (row.id, BrokerConnection.model_validate(row.payload))
            for row in await repository.all_connections(session, owner_id)
            if row.payload.get("provider") == "metaapi"
        ]
    provisioning = broker_provisioning.provisioning_client(token)
    try:
        visible = {account.account_id for account in await provisioning.accounts()}
    except LonoraError as failure:
        return failure.code
    finally:
        await provisioning.close()
    if any(config.account_id not in visible for _, config in rows):
        return "broker_token_mismatch"
    old = {config.secret_id for _, config in rows if config.secret_id}
    checked = sorted(connection for connection, _ in rows)
    async with _all_send_locked(db, owner_id, checked):
        async with db.sessions() as session, session.begin():
            # A connection made or removed since the check is caught here, and then
            # nothing changes (connect takes the same provisioning lock).
            await broker_provisioning.lock_provisioning(session, owner_id)
            # Owner first, as connection creation takes it, then the rows.
            await repository.lock_owner(session, owner_id)
            now = sorted(
                row.id
                for row in await repository.all_connections(session, owner_id)
                if row.payload.get("provider") == "metaapi"
            )
            if now != checked:
                return "broker_connection_changed"
            token_id = await secrets.write_in_session(session, METAAPI_TOKEN, token)
            for connection_id in checked:
                await repository.credentials_changed(
                    session, owner_id, connection_id, secret_id=token_id
                )
    for secret_id in {*old, pending} - {token_id}:
        await secrets.delete_unused(secret_id)
    return None


@asynccontextmanager
async def _all_send_locked(
    db: Database, owner_id: str, connection_ids: list[str]
) -> AsyncGenerator[None]:
    """Every account's send lock, in one order, so two holders never wait on each other."""
    async with db.sessions() as gate, gate.begin():
        for connection_id in connection_ids:
            await gate.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": send_lock_key(owner_id, connection_id)},
            )
        yield
