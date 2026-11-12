"""Push to the owner's phones (VISION 11.4).

One push per record, at its creation, to every phone whose sign-in session is live:
- a pending Trade Approval card (``approval_required``);
- a Settle Uncertain Operation card (``operation_uncertain``);
- a Secret card an agent's run raised and is waiting on (``secret_requested``);
- a broker health problem (``broker_token_rejected``, ``broker_account_undeployed``,
  ``broker_connection_lost``): one push per account and problem, the problem named by the
  account and the time it began, so a flapping connection pushes once per outage.

The text is the fixed catalog text of the event in the owner's language, under the agent's
name: no price, no volume, no account number and no model text leaves the server, and the
notification has no action button. A tap opens the conversation at the card, which reads the
live record; a push is never an approval (6.7, 6.10). Quiet hours do not hold these items.

Each push has an effect receipt written, in the same transaction that advances the owner's
cursor, before any network call. A receipt is never sent twice: a send whose outcome is unknown
(a timeout, a dropped connection, a restart) stays unconfirmed. So one record pushes once per
phone across restarts and across two gateways.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

from lonora_bus.attention import attention_text
from lonora_contracts.attention import BROKER_HEALTH_CODES
from lonora_core.user_error import LonoraError
from lonora_db.attention import mandatory_current, policy
from lonora_db.client import Database
from lonora_db.events import PUBLIC_CURSOR, publish_committed
from lonora_db.push_devices import (
    PushDevice,
    live_devices,
    prune_signed_out,
    push_token_hash,
)
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    EffectReceiptRow,
    EventRow,
    OwnerActionRow,
    PushDeviceRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.transactions import SettingsRepository
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("lonora.push")

PUSH_CODES = frozenset(
    {
        "approval_required",
        "operation_uncertain",
        "secret_requested",
        *BROKER_HEALTH_CODES,
    }
)
EVENTS_PER_TICK = 100
# Sends started per tick, each bounded by SEND_TIMEOUT_SECONDS, below the step's 120 s limit.
PUSHES_PER_TICK = 4
SEND_TIMEOUT_SECONDS = 20


class PushTransport(Protocol):
    async def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Delivery:
    receipt: str
    device_row: str
    token_hash: str
    message: dict[str, Any]


def cursor_key(owner_id: str) -> str:
    return "push-cursor:" + owner_id


def receipt_key(code: str, record: str, device_id: str) -> str:
    digest = hashlib.sha256(f"{code}\x00{record}\x00{device_id}".encode()).hexdigest()
    return "push:" + digest


async def push_lock(session: AsyncSession, owner_id: str) -> None:
    """Serializes one owner's push cursor across gateways; the receipt keys back it up."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "push:" + owner_id},
        )


async def push_record(session: AsyncSession, item: AttentionRow) -> tuple[str, int | None] | None:
    """The record an item pushes for, and the card's position in the item's conversation;
    None when the item does not push."""
    parameters = item.parameters
    row: TradeApprovalRow | TradingJournalRow | OwnerActionRow | None
    if item.code in BROKER_HEALTH_CODES:
        account, since = parameters.get("account_id"), parameters.get("since")
        if not account or not since:
            return None
        return f"{account}:{since}", None
    if item.code == "approval_required":
        row = await session.get(TradeApprovalRow, str(parameters.get("approval_id", "")))
        record = row.id if row else ""
    elif item.code == "operation_uncertain":
        row = await session.get(TradingJournalRow, str(parameters.get("operation_id", "")))
        record = row.operation_id if row else ""
    else:
        row = await session.get(OwnerActionRow, str(parameters.get("owner_action_id", "")))
        # Only a card an agent's run raised and is waiting on (11.4).
        if row is not None and (row.source != "agent" or not row.run_id):
            return None
        record = row.id if row else ""
    if row is None or not record:
        return None
    # The position only when the card lives in the conversation the push opens.
    return record, row.timeline_seq if row.thread_id == item.thread_id else None


async def item_deliveries(
    session: AsyncSession,
    owner_id: str,
    event: EventRow,
    devices: list[PushDevice],
    locale: str,
) -> list[Delivery]:
    """The receipts and messages of one attention.ready event; none when it does not push."""
    code = str(event.payload.get("code", ""))
    if code not in PUSH_CODES:
        return []
    item = await session.get(AttentionRow, str(event.payload.get("id", "")))
    if item is None or item.owner_id != owner_id or not await mandatory_current(session, item):
        return []
    found = await push_record(session, item)
    if found is None:
        return []
    record, anchor = found
    agent = await session.get(AgentRow, item.agent_id)
    data: dict[str, Any] = {"thread_id": item.thread_id}
    if anchor:
        data["around"] = anchor
    deliveries: list[Delivery] = []
    for device in devices:
        # One push per account and outage, whichever health code names it.
        kind = "broker_health" if code in BROKER_HEALTH_CODES else code
        key = receipt_key(kind, record, device.device_id)
        if await session.get(EffectReceiptRow, key):
            continue
        session.add(
            EffectReceiptRow(
                key=key,
                result={
                    "owner_id": owner_id,
                    "status": "submitted",
                    "code": code,
                    "record_id": record,
                    "device_id": device.device_id,
                },
            )
        )
        deliveries.append(
            Delivery(
                key,
                device.id,
                push_token_hash(device.token),
                {
                    "to": device.token,
                    "title": agent.name if agent else "Lonora",
                    "body": attention_text(code, locale),
                    "data": data,
                    "sound": "default",
                    "priority": "high",
                    "channelId": "attention",
                },
            )
        )
    return deliveries


async def dispatch_push(
    db: Database, owner_id: str, cipher: SecretCipher, transport: PushTransport
) -> int:
    """Send the pushes due for one owner; returns how many messages were handed to Expo."""
    deliveries: list[Delivery] = []
    async with db.sessions() as session:
        await publish_committed(session)
        await session.commit()
    async with db.sessions() as session, session.begin():
        await push_lock(session, owner_id)
        settings = SettingsRepository()
        stored = await settings.get(session, cursor_key(owner_id), fresh=True)
        if "last" not in stored:
            # The first run starts at the end of the stream: a push is sent when a record is
            # created, never for cards that were already waiting when push was installed.
            latest = await session.scalar(
                select(func.max(EventRow.payload[PUBLIC_CURSOR].as_integer())).where(
                    EventRow.owner_id == owner_id
                )
            )
            await settings.put(session, cursor_key(owner_id), {"last": int(latest or 0)})
            return 0
        cursor = int(stored["last"])
        await prune_signed_out(session, owner_id)
        events = (
            await session.scalars(
                select(EventRow)
                .where(
                    EventRow.owner_id == owner_id,
                    EventRow.kind == "attention.ready",
                    EventRow.payload[PUBLIC_CURSOR].as_integer() > cursor,
                )
                .order_by(EventRow.payload[PUBLIC_CURSOR].as_integer())
                .limit(EVENTS_PER_TICK)
            )
        ).all()
        if not events:
            return 0
        devices = await live_devices(session, owner_id, cipher)
        locale = (await policy(session, owner_id)).locale
        for event in events:
            # Each send may take up to its timeout: the rest waits for the next tick, so the
            # step never outlives its iteration with receipts it has not tried.
            if len(deliveries) >= PUSHES_PER_TICK:
                break
            cursor = int(event.payload[PUBLIC_CURSOR])
            if not devices:
                continue
            try:
                # One event that fails is skipped alone; the others keep flowing.
                async with session.begin_nested():
                    deliveries.extend(
                        await item_deliveries(session, owner_id, event, devices, locale)
                    )
            except Exception as error:
                log.error("push_item_failed code=%s", getattr(error, "code", type(error).__name__))
        await settings.put(session, cursor_key(owner_id), {"last": cursor})
    for delivery in deliveries:
        await send_one(db, transport, delivery)
    return len(deliveries)


async def send_one(db: Database, transport: PushTransport, delivery: Delivery) -> None:
    """One request per phone: a token Expo refuses never takes another phone's push with it."""
    outcome: dict[str, Any]
    try:
        async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
            tickets = await transport.send([delivery.message])
        outcome = ticket_outcome(tickets[0])
    except LonoraError as error:
        # Refused (4xx): Expo accepted nothing. Anything else: the outcome is unknown.
        status = "rejected" if error.code == "push_request_refused" else "ambiguous"
        outcome = {"status": status, "code": error.code}
    except Exception:
        outcome = {"status": "ambiguous", "code": "push_delivery_unconfirmed"}
    async with db.sessions() as session, session.begin():
        row = await session.get(EffectReceiptRow, delivery.receipt, with_for_update=True)
        if row is not None:
            row.result = {**row.result, **outcome}
        if outcome.get("code") == "DeviceNotRegistered":
            # Expo says the app is gone from that phone. Only that token: a phone that has
            # registered a new token since keeps it.
            await session.execute(
                delete(PushDeviceRow).where(
                    PushDeviceRow.id == delivery.device_row,
                    PushDeviceRow.token_hash == delivery.token_hash,
                )
            )
    if outcome["status"] != "confirmed":
        log.warning("push_unconfirmed status=%s", outcome["status"])


def ticket_outcome(ticket: dict[str, Any]) -> dict[str, Any]:
    if ticket.get("status") == "ok":
        return {"status": "confirmed", "ticket_id": str(ticket.get("id", ""))[:80]}
    details = ticket.get("details")
    code = (
        cast(dict[str, Any], details).get("error") if isinstance(details, dict) else None
    ) or "push_ticket_error"
    return {"status": "rejected", "code": str(code)[:80]}
