"""Connect a trading account from chat (VISION.md 9.2): provision, deploy, connect.

The connect tool raises a broker-destination Secret card for one login and server. When
the owner saves it, the password (and the MetaApi token, entered once) go to the broker
store and the card's result says ``provisioning: pending``. This gateway step then moves
each such card forward, one phase per pass, and records every phase on the card so a
restart resumes it:

- ``pending``: under the owner's connection lock, reuse the token's MetaApi account for
  this login and server or create one; its MetaApi id is recorded before any deploy.
- ``deploying``: deploy, and wait until MetaApi's terminal is connected to the broker.
- ``reading``: create the connection with the MetaApi-observed identity, then read the
  account once for balance, currency and trade permission.
- ``connected`` or ``failed``: the agent is woken once with fixed text (``broker_prompt``).

Provisioning makes account-entity calls only; orders still go only through the door.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from lonora_adapters.brokers.metaapi_provisioning import MetaApiProvisioning, ProvisionedAccount
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository, broker_identity_key
from lonora_db.client import Database
from lonora_db.owner_actions import continue_after_card
from lonora_db.schema import OwnerActionRow
from lonora_db.secrets import BROKER, METAAPI_TOKEN, metaapi_password_name
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .connections import verified_identity

log = logging.getLogger("lonora.broker.provisioning")
ACTIVE = ("pending", "deploying", "reading")
# How long a saved card may take to reach a connected terminal, then a first account read.
DEPLOY_DEADLINE = timedelta(minutes=15)
READ_DEADLINE = timedelta(minutes=5)
PLATFORM = re.compile(r"mt\s*-?\s*([45])", re.IGNORECASE)


def platform_of(server: str) -> str | None:
    """MT4 or MT5 when the server name says so (``Exness-MT5Trial16``); else None."""
    found = PLATFORM.search(server)
    return "mt" + found.group(1) if found else None


def provisioning_client(token: str) -> MetaApiProvisioning:
    return MetaApiProvisioning(token)


async def maintain_broker_provisioning(
    db: Database, brokers: Any, secrets: BrokerSecrets, owner_id: str
) -> None:
    async with db.sessions() as session:
        cards = [
            row.id
            for row in await session.scalars(
                select(OwnerActionRow).where(
                    OwnerActionRow.owner_id == owner_id,
                    OwnerActionRow.kind == "secret",
                    OwnerActionRow.status == "confirmed",
                )
            )
            if row.payload.get("destination") == BROKER and row.result.get("provisioning") in ACTIVE
        ]
    for card_id in cards:
        try:
            await advance(db, brokers, secrets, owner_id, card_id)
        except Exception:
            # One account's trouble never stops the others; the next pass retries.
            log.warning("broker_provisioning_pass_failed card=%s", card_id, exc_info=False)


async def _card(session: AsyncSession, owner_id: str, card_id: str) -> OwnerActionRow:
    row = await session.get(OwnerActionRow, card_id, with_for_update=True)
    assert row is not None and row.owner_id == owner_id
    return row


async def _record(session: AsyncSession, row: OwnerActionRow, **changes: Any) -> None:
    row.result = {**row.result, **changes}
    if changes.get("provisioning") in {"connected", "failed"}:
        # The agent that asked continues now, once, with the outcome.
        await continue_after_card(session, row)


async def advance(
    db: Database, brokers: Any, secrets: BrokerSecrets, owner_id: str, card_id: str
) -> None:
    async with db.sessions() as session:
        row = await _card(session, owner_id, card_id)
        phase, result, account = row.result.get("provisioning"), dict(row.result), row.payload
    started = str(result.get("started_at") or row.updated_at.isoformat())
    password_id = await secrets.named(metaapi_password_name(card_id))
    token_id = await secrets.named(METAAPI_TOKEN)
    if phase in {"pending", "deploying"} and (password_id is None or token_id is None):
        await _fail(db, secrets, owner_id, card_id, "broker_secret_required")
        return
    if phase == "pending":
        assert password_id is not None and token_id is not None
        await _provision(db, secrets, owner_id, card_id, account["account"], password_id, token_id)
    elif phase == "deploying":
        assert password_id is not None and token_id is not None
        await _deploy(db, secrets, owner_id, card_id, result, password_id, token_id, started)
    elif phase == "reading":
        await _read(db, brokers, owner_id, card_id, result)


async def _provision(
    db: Database,
    secrets: BrokerSecrets,
    owner_id: str,
    card_id: str,
    account: dict[str, str],
    password_id: str,
    token_id: str,
) -> None:
    repository = BrokerSessionRepository()
    provisioning = provisioning_client(await secrets.read(token_id))
    try:
        async with db.sessions() as session, session.begin():
            # Serialized with every other connection write of this owner (Q4).
            await repository.lock_owner(session, owner_id)
            row = await _card(session, owner_id, card_id)
            if row.result.get("provisioning") != "pending":
                return
            try:
                await repository.assert_unique(
                    session,
                    owner_id,
                    # Lonora's own uniqueness by the typed identity, before any MetaApi call.
                    {"provider": "metaapi", "account_id": "provisioning:" + card_id},
                    identity=account,
                )
                found, created = await provisioning.find_or_create(
                    login=account["login"],
                    server=account["server"],
                    platform=account["platform"],
                    password=await secrets.read(password_id),
                )
            except LonoraError as failure:
                await _record(session, row, provisioning="failed", code=failure.code)
                failed = failure.code
            else:
                failed = None
                # The MetaApi id is kept before any deploy: a retry finds this account.
                await _record(
                    session,
                    row,
                    provisioning="deploying",
                    metaapi_account_id=found.account_id,
                    region=found.region,
                    created=created,
                )
        if failed:
            await _forget(secrets, failed, password_id, token_id)
    finally:
        await provisioning.close()


async def _deploy(
    db: Database,
    secrets: BrokerSecrets,
    owner_id: str,
    card_id: str,
    result: dict[str, Any],
    password_id: str,
    token_id: str,
    started: str,
) -> None:
    token = await secrets.read(token_id)
    account_id = str(result["metaapi_account_id"])
    provisioning = provisioning_client(token)
    try:
        try:
            state = await provisioning.state(account_id)
            if not result.get("created") and not result.get("password_set"):
                # An account that already existed at MetaApi gets the password the owner
                # just typed, unless it is already deployed and connected with its own.
                if not (state.deployed and state.connected):
                    await provisioning.update_password(account_id, await secrets.read(password_id))
                    state = await (
                        provisioning.redeploy(account_id)
                        if state.deployed
                        else provisioning.deploy(account_id)
                    )
                async with db.sessions() as session, session.begin():
                    await _record(
                        session, await _card(session, owner_id, card_id), password_set=True
                    )
            elif state.state not in {"DEPLOYED", "DEPLOYING"}:
                state = await provisioning.deploy(account_id)
        except LonoraError as failure:
            await _fail(db, secrets, owner_id, card_id, failure.code)
            return
    finally:
        await provisioning.close()
    if not (state.deployed and state.connected):
        if utcnow() - datetime.fromisoformat(started) > DEPLOY_DEADLINE:
            code = (
                "broker_login_rejected"
                if state.connection_status == "DISCONNECTED_FROM_BROKER"
                else "broker_connect_timeout"
            )
            await _fail(db, secrets, owner_id, card_id, code)
        return
    await _connect(db, owner_id, card_id, state, token, token_id, password_id)


async def _connect(
    db: Database,
    owner_id: str,
    card_id: str,
    state: ProvisionedAccount,
    token: str,
    token_id: str,
    password_id: str,
) -> None:
    config = BrokerConnection(
        provider="metaapi",
        account_id=state.account_id,
        region=state.region,
        secret_id=token_id,
        enabled=True,
    )
    try:
        # Broker-observed identity from MetaApi's account entity, not the typed words.
        identity = await verified_identity(config, token)
    except LonoraError:
        return  # The next pass reads it again.
    repository = BrokerSessionRepository()
    async with db.sessions() as session, session.begin():
        await repository.lock_owner(session, owner_id)
        row = await _card(session, owner_id, card_id)
        if row.result.get("provisioning") != "deploying":
            return
        typed = row.payload["account"]
        if (broker_identity_key(identity) or ())[:2] != (broker_identity_key(typed) or ())[:2]:
            await _record(session, row, provisioning="failed", code="broker_identity_mismatch")
            return
        try:
            connection = await repository.create(
                session, owner_id, config.model_dump(mode="json"), broker_identity=identity
            )
        except LonoraError as failure:
            await _record(session, row, provisioning="failed", code=failure.code)
            return
        # The password this connection was provisioned with; rotation replaces it.
        connection.state = {**connection.state, "password_secret_id": password_id}
        await _record(
            session,
            row,
            provisioning="reading",
            connection_id=connection.id,
            connected_at=utcnow().isoformat(),
        )


async def _read(
    db: Database, brokers: Any, owner_id: str, card_id: str, result: dict[str, Any]
) -> None:
    facts: dict[str, Any] | None = None
    try:
        state = await brokers.account(owner_id, result["connection_id"])
        facts = {
            "balance": str(state.balance),
            "currency": state.currency,
            "trade_allowed": state.trade_allowed,
            "investor_mode": state.investor_mode,
        }
    except LonoraError:
        if utcnow() - datetime.fromisoformat(result["connected_at"]) <= READ_DEADLINE:
            return  # First synchronization of a new terminal can take a while.
    async with db.sessions() as session, session.begin():
        row = await _card(session, owner_id, card_id)
        if row.result.get("provisioning") == "reading":
            await _record(session, row, provisioning="connected", account=facts or {})


async def _fail(
    db: Database, secrets: BrokerSecrets, owner_id: str, card_id: str, code: str
) -> None:
    async with db.sessions() as session, session.begin():
        row = await _card(session, owner_id, card_id)
        if row.result.get("provisioning") not in ACTIVE:
            return
        await _record(session, row, provisioning="failed", code=code)
    await _forget(
        secrets,
        code,
        await secrets.named(metaapi_password_name(card_id)),
        await secrets.named(METAAPI_TOKEN),
    )


async def _forget(
    secrets: BrokerSecrets, code: str, password_id: str | None, token_id: str | None
) -> None:
    """A refused value is not kept: the next card asks for it again."""
    if password_id:
        await secrets.delete_unused(password_id)
    if token_id and code == "broker_token_rejected":
        await secrets.delete_unused(token_id)
