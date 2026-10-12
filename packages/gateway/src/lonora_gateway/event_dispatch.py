from typing import Any

from lonora_adapters.channels.telegram import TelegramAdapter
from lonora_adapters.channels.webhook import WebhookAdapter
from lonora_bus.runtime_events import RuntimeEvents
from lonora_channels.telegram.runtime import decode_update
from lonora_contracts.domain import MessageCreate
from lonora_contracts.events import EventEnvelope
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.messages import send_message
from lonora_db.schema import EffectReceiptRow, EventRow, IntegrationRow
from sqlalchemy import select

from .runtime import OwnerServices


def dispatch_event(bus: RuntimeEvents, event: EventEnvelope) -> None:
    bus.publish(event)


async def dispatch_channels(db: Database, services: OwnerServices) -> None:
    async with db.sessions() as session:
        rows = (
            await session.scalars(
                select(IntegrationRow).where(IntegrationRow.owner_id == services.owner_id)
            )
        ).all()
    for row in rows:
        config = row.payload
        if (
            not config.get("enabled")
            or config.get("type") not in {"telegram", "webhook"}
            or not config.get("secret_id")
        ):
            continue
        try:
            secret = await services.secrets.read(config["secret_id"])
            if config["type"] == "telegram":
                adapter = TelegramAdapter(secret)
                updates = await adapter.updates(int(row.state.get("update_offset", 0)))
                async with db.sessions() as session, session.begin():
                    locked = await session.get(IntegrationRow, row.id, with_for_update=True)
                    if locked is None:
                        continue
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
                    continue
                query = select(EventRow).where(
                    EventRow.owner_id == services.owner_id,
                    EventRow.cursor > int(locked.state.get("event_cursor", 0)),
                    EventRow.kind == "message.created",
                )
                if config.get("thread_id"):
                    query = query.where(EventRow.thread_id == config["thread_id"])
                events = (await session.scalars(query.order_by(EventRow.cursor).limit(100))).all()
                deliveries: list[tuple[str, str, dict[str, Any]]] = []
                for event in events:
                    locked.state = {**locked.state, "event_cursor": event.cursor}
                    if event.payload.get("role") != "assistant":
                        continue
                    destinations = (
                        config.get("allowed_destinations", [])
                        if config["type"] == "telegram"
                        else [config.get("url")]
                    )
                    for destination in destinations:
                        if not destination:
                            continue
                        receipt = (
                            "channel:" + row.id + ":" + str(event.cursor) + ":" + str(destination)
                        )
                        if await session.get(EffectReceiptRow, receipt):
                            continue
                        session.add(EffectReceiptRow(key=receipt, result={"status": "submitted"}))
                        deliveries.append((receipt, str(destination), event.payload))
            for receipt, destination, payload in deliveries:
                result: dict[str, Any]
                try:
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
