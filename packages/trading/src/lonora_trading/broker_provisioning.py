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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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
from lonora_db.secrets import BROKER, METAAPI_TOKEN, metaapi_password_name, secret_in_use
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .connections import verified_identity

log = logging.getLogger("lonora.broker.provisioning")
ACTIVE = ("pending", "deploying", "reading")
# Failures worth another pass before the deadline; any other code ends the card.
TRANSIENT = frozenset(
    {
        "broker_provisioning_timeout",
        "broker_provisioning_unavailable",
        "broker_provisioning_conflict",
        "broker_rate_limited",
        "broker_connection_timeout",
        "broker_connection_unavailable",
        "broker_identity_unavailable",
    }
)
# How long a saved card may take to reach a connected terminal, then a first account read.
DEPLOY_DEADLINE = timedelta(minutes=15)
READ_DEADLINE = timedelta(minutes=5)
# A deployed terminal the broker keeps refusing (DISCONNECTED_FROM_BROKER): a wrong
# password or server, reported after this long rather than at the full deadline.
LOGIN_DEADLINE = timedelta(minutes=3)
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
                select(OwnerActionRow)
                .where(
                    OwnerActionRow.owner_id == owner_id,
                    OwnerActionRow.kind == "secret",
                    OwnerActionRow.status == "confirmed",
                )
                .order_by(OwnerActionRow.created_at, OwnerActionRow.id)
            )
            if row.payload.get("destination") == BROKER and row.result.get("provisioning") in ACTIVE
        ]
    for card_id in cards:
        try:
            await advance(db, brokers, secrets, owner_id, card_id)
        except Exception as error:
            # One account's trouble never stops the others; the next pass retries.
            log.warning(
                "broker_provisioning_pass_failed card=%s type=%s", card_id, type(error).__name__
            )


async def _card(session: AsyncSession, owner_id: str, card_id: str) -> OwnerActionRow:
    row = await session.get(OwnerActionRow, card_id, with_for_update=True)
    assert row is not None and row.owner_id == owner_id
    return row


async def _record(session: AsyncSession, row: OwnerActionRow, **changes: Any) -> None:
    row.result = {**row.result, **changes}
    if changes.get("provisioning") in {"connected", "failed"}:
        # The agent that asked continues now, once, with the outcome.
        await continue_after_card(session, row)


def _late(since: str, limit: timedelta = DEPLOY_DEADLINE) -> bool:
    return utcnow() - datetime.fromisoformat(since) > limit


async def advance(
    db: Database, brokers: Any, secrets: BrokerSecrets, owner_id: str, card_id: str
) -> None:
    async with db.sessions() as session:
        row = await session.get(OwnerActionRow, card_id)
        assert row is not None and row.owner_id == owner_id
        phase, result, payload = row.result.get("provisioning"), dict(row.result), row.payload
        started = str(result.get("started_at") or row.updated_at.isoformat())
        subject = row.subject
    if payload.get("purpose", "connect") != "connect":
        await _change_credentials(db, brokers, secrets, owner_id, card_id, payload)
        return
    password_id = await secrets.named(metaapi_password_name(card_id))
    token_id = await secrets.named(METAAPI_TOKEN)
    failing = Failing(db, secrets, owner_id, card_id, str(phase), result)
    if phase in {"pending", "deploying"} and (password_id is None or token_id is None):
        await failing("broker_secret_required")
        return
    try:
        if phase == "pending":
            assert password_id is not None and token_id is not None
            await _provision(
                db, secrets, failing, payload["account"], subject, password_id, token_id, started
            )
        elif phase == "deploying":
            assert password_id is not None and token_id is not None
            await _deploy(db, failing, result, password_id, token_id, started, secrets)
        elif phase == "reading":
            await _read(db, brokers, owner_id, card_id, result)
    except Exception:
        # Any other failure retries until the deadline, then ends the card: it never
        # holds the account "in progress" forever.
        if phase in {"pending", "deploying"} and _late(started):
            await failing("broker_provisioning_failed")
        raise


async def _change_credentials(
    db: Database,
    brokers: Any,
    secrets: BrokerSecrets,
    owner_id: str,
    card_id: str,
    payload: dict[str, Any],
) -> None:
    """A rotation or token card (9.3): one pass does it and wakes the agent once."""
    from .broker_manage import replace_token, rotate_password

    async with db.sessions() as session:
        card = await session.get(OwnerActionRow, card_id)
        assert card is not None
    change = rotate_password if payload["purpose"] == "rotate_password" else replace_token
    try:
        code = await change(db, brokers, secrets, owner_id, card)
    except Exception as error:
        # A change card always ends: the agent hears it, and the next pass leaves it.
        log.warning(
            "broker_credential_change_failed card=%s type=%s", card_id, type(error).__name__
        )
        code = "broker_credential_change_failed"
    async with db.sessions() as session, session.begin():
        row = await _card(session, owner_id, card_id)
        if row.result.get("provisioning") != "pending":
            return
        if code is None:
            await _record(session, row, provisioning="connected")
        else:
            await _record(session, row, provisioning="failed", code=code)
    if code is not None:
        for name in (metaapi_password_name(card_id), "metaapi_token_next:" + card_id):
            found = await secrets.named(name)
            if found:
                await secrets.delete_unused(found)


class Failing:
    """Ends one card as failed, only from the phase this pass started in, and cleans up:
    the refused password is forgotten, and an account Lonora itself created at MetaApi
    is removed (no connection and no journal row ever referred to it)."""

    def __init__(
        self,
        db: Database,
        secrets: BrokerSecrets,
        owner_id: str,
        card_id: str,
        phase: str,
        result: dict[str, Any],
    ):
        self.db, self.secrets, self.owner_id, self.card_id = db, secrets, owner_id, card_id
        self.phase, self.result = phase, result

    async def __call__(self, code: str, provisioning: MetaApiProvisioning | None = None) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await _card(session, self.owner_id, self.card_id)
            if row.result.get("provisioning") != self.phase:
                return  # Another pass moved this card on.
            await _record(session, row, provisioning="failed", code=code)
            created = row.result.get("created") is True
            account_id = row.result.get("metaapi_account_id")
        if code == "broker_token_rejected":
            # Whether the refused token stays (a live connection still names it) decides
            # what the agent is told to do next.
            token = await self.secrets.named(METAAPI_TOKEN)
            async with self.db.sessions() as session, session.begin():
                kept = token is not None and await secret_in_use(session, self.owner_id, token)
                row = await _card(session, self.owner_id, self.card_id)
                row.result = {**row.result, "token_kept": kept}
        if created and account_id and provisioning is not None:
            try:
                await provisioning.remove(str(account_id))
            except LonoraError:
                log.warning("broker_provisioning_cleanup_failed card=%s", self.card_id)
        await _forget(
            self.secrets,
            code,
            await self.secrets.named(metaapi_password_name(self.card_id)),
            await self.secrets.named(METAAPI_TOKEN),
        )


async def _provision(
    db: Database,
    secrets: BrokerSecrets,
    failing: Failing,
    account: dict[str, str],
    subject: str,
    password_id: str,
    token_id: str,
    started: str,
) -> None:
    repository = BrokerSessionRepository()
    owner_id, card_id = failing.owner_id, failing.card_id
    provisioning = provisioning_client(await secrets.read(token_id))
    failed: str | None = None
    try:
        # Serialized per owner by an advisory lock (Q4): it keeps a second account from
        # being made, and blocks no row, so the door journals orders while MetaApi works.
        async with provisioning_locked(db, owner_id):
            async with db.sessions() as session, session.begin():
                row = await _card(session, owner_id, card_id)
                if row.result.get("provisioning") != "pending":
                    return
                try:
                    if await other_card_active(session, owner_id, subject, card_id):
                        raise LonoraError("broker_connect_in_progress", 409)
                    await repository.assert_unique(
                        session,
                        owner_id,
                        # Lonora's own uniqueness by the typed identity, before any MetaApi call.
                        {"provider": "metaapi", "account_id": "provisioning:" + card_id},
                        identity=account,
                    )
                except LonoraError as failure:
                    failed = failure.code
            if failed is None:
                try:
                    # No transaction and no row lock while MetaApi works (up to minutes).
                    found, created = await provisioning.find_or_create(
                        login=account["login"],
                        server=account["server"],
                        platform=account["platform"],
                        password=await secrets.read(password_id),
                        # Every create sent for this card is the same MetaApi transaction.
                        request_key=card_id,
                    )
                except LonoraError as failure:
                    if failure.code in TRANSIENT and not _late(started):
                        return  # The next pass tries again; a lost create is found by then.
                    failed = failure.code
                else:
                    async with db.sessions() as session, session.begin():
                        row = await _card(session, owner_id, card_id)
                        if row.result.get("provisioning") != "pending":
                            return
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
            await failing(failed)
    finally:
        await provisioning.close()


def provisioning_key(owner_id: str) -> str:
    return "broker-provision:" + owner_id


async def lock_provisioning(session: AsyncSession, owner_id: str) -> None:
    """The owner's provisioning lock, for this transaction (an advisory lock: no row)."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": provisioning_key(owner_id)},
    )


@asynccontextmanager
async def provisioning_locked(db: Database, owner_id: str) -> AsyncGenerator[None]:
    async with db.sessions() as gate, gate.begin():
        await lock_provisioning(gate, owner_id)
        yield


async def other_card_active(
    session: AsyncSession, owner_id: str, subject: str, card_id: str
) -> bool:
    """Another saved connect card for the same account is still being provisioned."""
    for row in await session.scalars(
        select(OwnerActionRow).where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == "secret",
            OwnerActionRow.status == "confirmed",
            # Cards saved before the subject named its purpose used the earlier form.
            OwnerActionRow.subject.in_(
                {subject, subject.replace("secret:broker:connect:", "secret:broker:", 1)}
            ),
            OwnerActionRow.id != card_id,
        )
    ):
        if row.result.get("provisioning") in ACTIVE:
            return True
    return False


async def _deploy(
    db: Database,
    failing: Failing,
    result: dict[str, Any],
    password_id: str,
    token_id: str,
    started: str,
    secrets: BrokerSecrets,
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
                    row = await _card(session, failing.owner_id, failing.card_id)
                    if row.result.get("provisioning") != "deploying":
                        return
                    await _record(session, row, password_set=True)
            elif state.state not in {"DEPLOYED", "DEPLOYING"}:
                state = await provisioning.deploy(account_id)
        except LonoraError as failure:
            if failure.code not in TRANSIENT or _late(started):
                await failing(failure.code, provisioning)
            return
        if not (state.deployed and state.connected):
            refused = state.deployed and state.connection_status == "DISCONNECTED_FROM_BROKER"
            if _late(started) or (refused and _late(started, LOGIN_DEADLINE)):
                code = (
                    "broker_login_rejected"
                    if state.connection_status == "DISCONNECTED_FROM_BROKER"
                    else "broker_connect_timeout"
                )
                await failing(code, provisioning)
            return
        code = await _connect(db, failing, state, token, token_id, password_id)
        if code is not None and (code not in TRANSIENT or _late(started)):
            await failing(code, provisioning)
    finally:
        await provisioning.close()


async def _connect(
    db: Database,
    failing: Failing,
    state: ProvisionedAccount,
    token: str,
    token_id: str,
    password_id: str,
) -> str | None:
    """Create the connection; the failure code when it cannot be, else None."""
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
    except LonoraError as failure:
        return failure.code
    repository = BrokerSessionRepository()
    async with db.sessions() as session, session.begin():
        await repository.lock_owner(session, failing.owner_id)
        row = await _card(session, failing.owner_id, failing.card_id)
        if row.result.get("provisioning") != "deploying":
            return None
        typed = row.payload["account"]
        if (broker_identity_key(identity) or ())[:2] != (broker_identity_key(typed) or ())[:2]:
            return "broker_identity_mismatch"
        try:
            connection = await repository.create(
                session, failing.owner_id, config.model_dump(mode="json"), broker_identity=identity
            )
        except LonoraError as failure:
            return failure.code
        # The password this connection was provisioned with; rotation replaces it.
        connection.state = {
            **connection.state,
            "password_secret_id": password_id,
            # Disconnect removes at MetaApi only accounts Lonora itself created (Q8).
            "provisioned_by_lonora": failing.result.get("created") is True,
        }
        await _record(
            session,
            row,
            provisioning="reading",
            connection_id=connection.id,
            connected_at=utcnow().isoformat(),
            # What the wake names: MetaApi's observation, not the agent's typed words.
            observed={key: identity.get(key) for key in ("login", "server", "broker")},
        )
    return None


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
        if not _late(result["connected_at"], READ_DEADLINE):
            return  # First synchronization of a new terminal can take a while.
    async with db.sessions() as session, session.begin():
        row = await _card(session, owner_id, card_id)
        if row.result.get("provisioning") == "reading":
            await _record(session, row, provisioning="connected", account=facts or {})


async def _forget(
    secrets: BrokerSecrets, code: str, password_id: str | None, token_id: str | None
) -> None:
    """A refused value is not kept: the next card asks for it again."""
    if password_id:
        await secrets.delete_unused(password_id)
    if token_id and code == "broker_token_rejected":
        await secrets.delete_unused(token_id)
