"""Durable notification decisions reuse event publication and effect receipts."""

from datetime import timedelta
from typing import Any

from lonora_contracts.attention import AttentionClassification, AttentionPolicy
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import (
    AttentionRow,
    BrokerSessionRow,
    EffectReceiptRow,
    EventRow,
    SettingRow,
    SuperBotRequestRow,
    TicketRow,
    TradeApprovalRow,
)
from .transactions import SettingsRepository, owned_agent, owned_thread


def attention_data(row: AttentionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "importance": row.importance,
        "code": row.code,
        "status": row.status,
        "parameters": row.parameters,
        "source_events": row.source_events,
        "source_count": row.source_count,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def policy(session: AsyncSession, owner_id: str) -> AttentionPolicy:
    return AttentionPolicy.model_validate(
        await SettingsRepository().get(session, "attention-policy:" + owner_id)
    )


async def mandatory_current(session: AsyncSession, row: AttentionRow) -> bool:
    if row.code == "super_bot_authorization":
        proposal = await session.get(
            SuperBotRequestRow, row.parameters.get("super_bot_request_id", "")
        )
        return (
            proposal is not None
            and proposal.owner_id == row.owner_id
            and proposal.status == "pending"
            and proposal.expires_at > utcnow()
        )
    if row.code == "emergency_stop":
        return (await SettingsRepository().get(session, "trading_control")).get(
            "emergency_stop"
        ) is True
    if row.code == "approval_required":
        approval = await session.get(TradeApprovalRow, row.parameters.get("approval_id", ""))
        return (
            approval is not None
            and approval.owner_id == row.owner_id
            and approval.status == "pending"
        )
    if row.code == "broker_degraded":
        broker = await session.get(BrokerSessionRow, row.parameters.get("account_id", ""))
        return (
            broker is not None
            and broker.owner_id == row.owner_id
            and broker.state.get("broker_recovery", {}).get("status")
            in {"degraded", "disconnected", "recovering", "reconciling"}
        )
    if row.code == "task_review":
        task = await session.get(TicketRow, row.parameters.get("task_id", ""))
        return (
            task is not None
            and task.owner_id == row.owner_id
            and task.state.get("task", {}).get("status") == "failed"
        )
    return False


async def decide_attention(
    session: AsyncSession,
    event: EventRow,
    classification: AttentionClassification,
    *,
    agent_id: str,
    thread_id: str,
    parameters: dict[str, Any],
    coalesce_scope: str,
    suppression_code: str | None = None,
) -> AttentionRow | None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "attention:" + event.owner_id},
        )
    receipt_key = "attention-source:" + event.owner_id + ":" + str(event.cursor)
    prior = await session.get(EffectReceiptRow, receipt_key)
    if prior:
        return await session.get(AttentionRow, prior.result.get("notification_id", ""))
    await owned_agent(session, event.owner_id, agent_id)
    await owned_thread(session, event.owner_id, thread_id)
    settings = await policy(session, event.owner_id)
    current_transition = suppression_code is None
    category = classification.importance
    if category == "silent":
        suppression_code = suppression_code or "runtime_only"
    elif category == "opportunity" and not settings.opportunities:
        suppression_code = suppression_code or "owner_opportunity_preference"
    elif category == "informational" and not settings.informational:
        suppression_code = suppression_code or "owner_informational_preference"
    decision: dict[str, Any] = {
        "source_event": event.cursor,
        "agent_id": agent_id,
        "thread_id": thread_id,
        "importance": category,
        "code": classification.code,
        "transition": classification.transition,
    }
    logical = request_hash(
        {
            "scope": [
                event.owner_id,
                agent_id,
                coalesce_scope,
                classification.code,
                classification.transition,
            ]
        }
    )
    logical_receipt_key = "attention-logical:" + event.owner_id + ":" + logical
    logical_receipt = await session.get(EffectReceiptRow, logical_receipt_key)
    if logical_receipt:
        identifier = logical_receipt.result.get("notification_id")
        session.add(
            EffectReceiptRow(
                key=receipt_key,
                result={
                    **decision,
                    "status": "deduplicated",
                    "notification_id": identifier,
                    "reason_code": "same_transition",
                },
            )
        )
        return await session.get(AttentionRow, identifier) if identifier else None
    now = utcnow()
    group = request_hash({"scope": [event.owner_id, agent_id, coalesce_scope]})
    # Once runtime truth advances, an old unread alert cannot keep claiming the
    # previous state. Keep its source/history; remove only its live projection.
    superseded = await session.scalars(
        select(AttentionRow)
        .where(
            AttentionRow.owner_id == event.owner_id,
            AttentionRow.coalesce_key == group,
            AttentionRow.status.in_(["pending", "ready"] if category == "silent" else ["ready"]),
            AttentionRow.logical_key != logical,
        )
        .with_for_update()
    )
    for old in superseded:
        if not current_transition:
            continue
        old.status, old.version, old.updated_at = "suppressed", old.version + 1, now
        old.parameters = {**old.parameters, "suppression_code": "attention_superseded_state"}
        emit(
            session,
            event.owner_id,
            "attention.updated",
            agent_id=old.agent_id,
            thread_id=old.thread_id,
            payload=attention_data(old),
        )
    if suppression_code:
        session.add(
            EffectReceiptRow(
                key=receipt_key,
                result={**decision, "status": "suppressed", "reason_code": suppression_code},
            )
        )
        session.add(
            EffectReceiptRow(
                key=logical_receipt_key,
                result={"status": "suppressed", "reason_code": suppression_code},
            )
        )
        return None
    existing = await session.scalar(
        select(AttentionRow).where(
            AttentionRow.owner_id == event.owner_id, AttentionRow.logical_key == logical
        )
    )
    if existing:
        session.add(
            EffectReceiptRow(
                key=receipt_key,
                result={
                    **decision,
                    "status": "deduplicated",
                    "notification_id": existing.id,
                    "reason_code": "same_transition",
                },
            )
        )
        return existing
    urgent = category in {"critical", "action_required"}
    row = await session.scalar(
        select(AttentionRow)
        .where(
            AttentionRow.owner_id == event.owner_id,
            AttentionRow.coalesce_key == group,
            AttentionRow.status == "pending",
            AttentionRow.due_at > now,
        )
        .with_for_update()
    )
    if row:
        row.code, row.importance, row.parameters = classification.code, category, parameters
        row.source_events = (row.source_events + [event.cursor])[-16:]
        row.source_count, row.version, row.updated_at = row.source_count + 1, row.version + 1, now
        if urgent:
            row.due_at = now
    else:
        row = AttentionRow(
            id=stable_id(event.owner_id, "attention:" + logical),
            owner_id=event.owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            logical_key=logical,
            coalesce_key=group,
            importance=category,
            code=classification.code,
            parameters=parameters,
            status="pending",
            source_events=[event.cursor],
            source_count=1,
            version=1,
            due_at=now if urgent else now + timedelta(seconds=3),
        )
        session.add(row)
    await session.flush()
    session.add(EffectReceiptRow(key=logical_receipt_key, result={"notification_id": row.id}))
    session.add(
        EffectReceiptRow(
            key=receipt_key,
            result={
                **decision,
                "status": "coalesced" if row.source_count > 1 else "pending",
                "notification_id": row.id,
                "reason_code": "related_transition"
                if row.source_count > 1
                else "meaningful_transition",
            },
        )
    )
    emit(
        session,
        event.owner_id,
        "attention.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=attention_data(row),
    )
    return row


async def acknowledge(session: AsyncSession, owner_id: str, identifier: str) -> AttentionRow:
    row = await session.get(AttentionRow, identifier, with_for_update=True)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("attention_not_found", 404)
    if row.status not in {"seen", "suppressed"}:
        row.status, row.version, row.updated_at = "seen", row.version + 1, utcnow()
        emit(
            session,
            owner_id,
            "attention.updated",
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload=attention_data(row),
        )
    return row


async def set_cursor(session: AsyncSession, owner_id: str, cursor: int) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "attention:" + owner_id},
        )
    key = "attention-cursor:" + owner_id
    row = await session.get(SettingRow, key, with_for_update=True)
    if row:
        row.payload = {"cursor": max(cursor, int(row.payload.get("cursor", 0)))}
    else:
        session.add(SettingRow(key=key, payload={"cursor": cursor}))
