import asyncio
from typing import Any

from lonora_adapters.channels.telegram import TelegramAdapter
from lonora_adapters.channels.webhook import WebhookAdapter
from lonora_bus.attention import attention_text
from lonora_bus.runtime_events import RuntimeEvents
from lonora_channels.telegram.runtime import decode_update
from lonora_contracts.domain import MessageCreate
from lonora_contracts.events import EventEnvelope
from lonora_core.user_error import LonoraError
from lonora_db.attention import mandatory_current, policy
from lonora_db.client import Database
from lonora_db.events import PUBLIC_CURSOR, publish_committed
from lonora_db.item_failures import ItemGuard, blocked
from lonora_db.messages import send_message
from lonora_db.schema import (
    AttentionRow,
    EffectReceiptRow,
    EventRow,
    IntegrationRow,
)
from sqlalchemy import select

from .runtime import OwnerServices

# A channel request never holds the delivery loop longer than this.
CHANNEL_TIMEOUT_SECONDS = 30


def dispatch_event(bus: RuntimeEvents, event: EventEnvelope) -> None:
    bus.publish(event)


async def dispatch_channels(db: Database, services: OwnerServices) -> None:
    async with db.sessions() as session:
        await publish_committed(session)
        rows = (
            await session.scalars(
                select(IntegrationRow).where(
                    IntegrationRow.owner_id == services.owner_id,
                    ~blocked("integration", IntegrationRow.id),
                )
            )
        ).all()
    # One integration that raises (an unreachable Telegram, a malformed update) backs
    # off alone; the other integrations keep receiving and delivering.
    # Each network call has its own timeout; the item limit only bounds a whole batch of
    # deliveries, below the step's iteration timeout.
    guard = ItemGuard(db, "integration", quarantine_after=None, timeout=100)
    await guard.prepare(row.id for row in rows)
    for row in rows:

        async def dispatch(row: IntegrationRow = row) -> None:
            await dispatch_integration(db, services, row)

        await guard.run(row.id, services.owner_id, dispatch)


async def dispatch_integration(db: Database, services: OwnerServices, row: IntegrationRow) -> None:
    config = row.payload
    if (
        not config.get("enabled")
        or config.get("type") not in {"telegram", "webhook"}
        or not config.get("secret_id")
    ):
        return
    try:
        secret = await services.secrets.read(config["secret_id"])
        if config["type"] == "telegram":
            adapter = TelegramAdapter(secret)
            async with asyncio.timeout(CHANNEL_TIMEOUT_SECONDS):
                updates = await adapter.updates(int(row.state.get("update_offset", 0)))
            async with db.sessions() as session, session.begin():
                locked = await session.get(IntegrationRow, row.id, with_for_update=True)
                if locked is None:
                    return
                for update in updates:
                    if config.get("thread_id"):
                        incoming = decode_update(update, config["thread_id"])
                        if incoming and incoming.destination in config.get(
                            "allowed_destinations", []
                        ):
                            await send_message(
                                session,
                                services.owner_id,
                                incoming.thread_id,
                                MessageCreate(
                                    content=incoming.content, client_nonce=incoming.external_id
                                ),
                            )
                    locked.state = {
                        **locked.state,
                        "update_offset": max(
                            int(locked.state.get("update_offset", 0)),
                            int(update["update_id"]) + 1,
                        ),
                    }
        async with db.sessions() as session, session.begin():
            locked = await session.get(IntegrationRow, row.id, with_for_update=True)
            if locked is None:
                return
            query = select(EventRow).where(
                EventRow.owner_id == services.owner_id,
                EventRow.payload[PUBLIC_CURSOR].as_integer()
                > int(locked.state.get("event_cursor", 0)),
                EventRow.kind.in_(["message.created", "attention.ready"]),
            )
            if config.get("thread_id"):
                query = query.where(EventRow.thread_id == config["thread_id"])
            events = (
                await session.scalars(
                    query.order_by(EventRow.payload[PUBLIC_CURSOR].as_integer()).limit(100)
                )
            ).all()
            deliveries: list[tuple[str, str, dict[str, Any]]] = []
            for event in events:
                locked.state = {
                    **locked.state,
                    "event_cursor": int(event.payload[PUBLIC_CURSOR]),
                }
                identity = str(event.cursor)
                outbound = event.payload
                if event.kind == "attention.ready":
                    notification = await session.get(AttentionRow, event.payload.get("id", ""))
                    if (
                        notification is None
                        or notification.owner_id != services.owner_id
                        or notification.status != "ready"
                        or notification.importance not in {"critical", "action_required"}
                    ):
                        continue
                    if not await mandatory_current(session, notification):
                        skip_key = "attention-channel-skip:" + row.id + ":" + notification.id
                        if not await session.get(EffectReceiptRow, skip_key):
                            session.add(
                                EffectReceiptRow(
                                    key=skip_key,
                                    result={
                                        "owner_id": services.owner_id,
                                        "status": "suppressed",
                                        "code": "attention_superseded_state",
                                        "notification_id": notification.id,
                                        "integration_id": row.id,
                                    },
                                )
                            )
                        continue
                    settings = await policy(session, services.owner_id)
                    outbound = {"content": attention_text(notification.code, settings.locale)}
                    identity = "attention:" + notification.id
                elif event.payload.get("role") != "assistant":
                    continue
                destinations = (
                    config.get("allowed_destinations", [])
                    if config["type"] == "telegram"
                    else [config.get("url")]
                )
                for destination in destinations:
                    if not destination:
                        continue
                    receipt = "channel:" + row.id + ":" + identity + ":" + str(destination)
                    if await session.get(EffectReceiptRow, receipt):
                        continue
                    session.add(EffectReceiptRow(key=receipt, result={"status": "submitted"}))
                    deliveries.append((receipt, str(destination), outbound))
        for receipt, destination, payload in deliveries:
            result: dict[str, Any]
            try:
                async with asyncio.timeout(CHANNEL_TIMEOUT_SECONDS):
                    if config["type"] == "telegram":
                        result = await TelegramAdapter(secret).send(
                            destination, str(payload.get("content", ""))
                        )
                    else:
                        result = await WebhookAdapter(secret).send(
                            destination, str(payload.get("content", ""))
                        )
                result = {"status": "confirmed", **result}
            except Exception:
                result = {"status": "ambiguous", "code": "channel_delivery_unconfirmed"}
            async with db.sessions() as session, session.begin():
                delivery = await session.get(EffectReceiptRow, receipt, with_for_update=True)
                if delivery:
                    delivery.result = result
    except LonoraError as error:
        async with db.sessions() as session, session.begin():
            locked = await session.get(IntegrationRow, row.id, with_for_update=True)
            if locked:
                locked.state = {**locked.state, "code": error.code}
