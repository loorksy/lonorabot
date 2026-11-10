"""Durable notification decisions reuse event publication and effect receipts."""

from datetime import timedelta
from typing import Any

from lonora_contracts.attention import (
    AttentionClassification,
    AttentionPolicy,
    OwnerNotifyRequest,
)
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import IN_PROGRESS_STATUSES, UNRESOLVED_STATUSES
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .owner_profile import reach_me_policy
from .schema import (
    AttentionRow,
    BrokerSessionRow,
    EffectReceiptRow,
    EventRow,
    SettingRow,
    TicketRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from .transactions import SettingsRepository, owned_agent, owned_thread

# Raised by the deterministic watchdog and the maintenance isolation, never by a model.
SYSTEM_ATTENTION = {
    "maintenance_item_quarantined": "important_change",
    "run_quarantined": "action_required",
    "operation_unresolved": "action_required",
    # A close left a position without its exit orders; open until protected or closed.
    "position_unprotected": "action_required",
    "gateway_degraded": "important_change",
}


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
    if row.code == "operation_uncertain":
        journal = await session.get(TradingJournalRow, row.parameters.get("operation_id", ""))
        return (
            journal is not None
            and journal.owner_id == row.owner_id
            and journal.status == "ambiguous"
        )
    if row.code == "operation_unresolved":
        journal = await session.get(TradingJournalRow, row.parameters.get("operation_id", ""))
        return (
            journal is not None
            and journal.owner_id == row.owner_id
            and journal.status in IN_PROGRESS_STATUSES | UNRESOLVED_STATUSES
        )
    if row.code == "run_quarantined":
        return True
    if row.code == "position_unprotected":
        # Withdrawn by lonora_trading.protection only once the broker shows the position
        # protected again or closed; until then it is current.
        return True
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
        state: dict[str, Any] = task.state.get("task", {}) if task is not None else {}
        return (
            task is not None
            and task.owner_id == row.owner_id
            and (
                state.get("status") == "failed"
                or (
                    state.get("status") == "waiting"
                    and state.get("waiting_reason") == "owner_attention"
                )
            )
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


def publish_ready(session: AsyncSession, row: AttentionRow, suppression: str | None) -> bool:
    """Settle a due pending item as ready, or suppressed with its reason; True when ready."""
    row.status, row.version, row.updated_at = (
        "suppressed" if suppression else "ready",
        row.version + 1,
        utcnow(),
    )
    if suppression:
        row.parameters = {**row.parameters, "suppression_code": suppression}
    emit(
        session,
        row.owner_id,
        "attention.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=attention_data(row),
    )
    if suppression:
        return False
    emit(
        session,
        row.owner_id,
        "attention.ready",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=attention_data(row),
    )
    return True


# An Agent's own notifications per rolling hour; a dedupe key notifies once.
NOTIFY_LIMIT_PER_HOUR = 6
# Agent-declared critical alerts per owner and rolling hour, across every agent. A
# critical alert passes quiet hours and activity-only; beyond this it is an important
# change, so injected text in many wakes cannot ring the owner without end.
CRITICAL_LIMIT_PER_HOUR = 6
MAX_NOTIFY_LIFETIME = timedelta(days=31)
NOTIFY_DELIVERY = "in_app"
NOTIFY_EVENT = "agent.owner_notify"


async def notify_owner(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    thread_id: str,
    request: OwnerNotifyRequest,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """An Agent-raised owner attention item under the owner's reach-me rules.

    One item per Agent and dedupe key, at most NOTIFY_LIMIT_PER_HOUR per Agent. Quiet
    hours hold everything but critical items until they end; beyond
    CRITICAL_LIMIT_PER_HOUR critical alerts per owner, a critical one counts as an
    important change. Under reach-me "activity
    only" a non-critical alert raises no item (``activity_only``): the Agent says it in
    its reply, which reaches its conversation and the Activity list. Delivery is in the
    app until off-app delivery exists. The item grants nothing.
    """
    now = utcnow()
    if request.expires_at is not None and not now < request.expires_at <= now + (
        MAX_NOTIFY_LIFETIME
    ):
        raise LonoraError("owner_notify_expiry_invalid", 422)
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "attention:" + owner_id},
        )
    receipt_key = "owner-notify:" + request_hash(
        {"owner_id": owner_id, "agent_id": agent_id, "dedupe_key": request.dedupe_key}
    )
    prior = await session.get(EffectReceiptRow, receipt_key)
    if prior is not None:
        item = await session.get(AttentionRow, prior.result.get("attention_id") or "")
        return {
            **prior.result,
            "deduplicated": True,
            **({"attention": attention_data(item)} if item else {}),
        }
    # Every alert counts, also one kept in activity only or held for quiet hours.
    recent = await session.scalar(
        select(func.count())
        .select_from(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.agent_id == agent_id,
            EventRow.kind == NOTIFY_EVENT,
            EventRow.created_at > now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= NOTIFY_LIMIT_PER_HOUR:
        raise LonoraError("owner_notify_rate_limited", 429)
    reach = await reach_me_policy(session, owner_id)
    critical = request.importance == "critical"
    if critical:
        criticals = await session.scalar(
            select(func.count())
            .select_from(EventRow)
            .where(
                EventRow.owner_id == owner_id,
                EventRow.kind == NOTIFY_EVENT,
                EventRow.created_at > now - timedelta(hours=1),
                EventRow.payload["importance"].as_string() == "critical",
            )
        )
        if (criticals or 0) >= CRITICAL_LIMIT_PER_HOUR:
            request = request.model_copy(update={"importance": "important_change"})
            critical = False
    held_until = None if critical else reach.quiet_until(now)
    parameters: dict[str, Any] = {
        "execution_authorized": False,
        "summary": request.summary,
        "evidence_refs": request.evidence_refs,
        "dedupe_key": request.dedupe_key,
        "delivery": NOTIFY_DELIVERY,
        **({"valid_until": request.expires_at.isoformat()} if request.expires_at else {}),
    }
    event = EventRow(
        owner_id=owner_id,
        kind=NOTIFY_EVENT,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
        payload={"importance": request.importance, **parameters},
    )
    session.add(event)
    await session.flush()
    row = await decide_attention(
        session,
        event,
        AttentionClassification(
            importance=request.importance,
            code="agent_notification",
            resource_id=request.dedupe_key,
            transition=request.dedupe_key,
        ),
        agent_id=agent_id,
        thread_id=thread_id,
        parameters=parameters,
        coalesce_scope="notify:" + request.dedupe_key,
        suppression_code="owner_reach_me_activity"
        if reach.channel == "activity" and not critical
        else None,
    )
    if row is None:
        status = (
            "activity_only"
            if reach.channel == "activity" and not critical
            else "not_shown_owner_preference"
        )
    elif held_until is not None:
        row.due_at = held_until
        status = "held_for_quiet_hours"
    elif request.importance in {"critical", "action_required"}:
        publish_ready(session, row, None)
        status = "ready"
    else:
        status = "pending"
    result: dict[str, Any] = {
        "status": status,
        "attention_id": row.id if row else None,
        "delivery": NOTIFY_DELIVERY,
        **({"held_until": held_until.isoformat()} if row and held_until else {}),
    }
    session.add(EffectReceiptRow(key=receipt_key, result=result))
    return {**result, **({"attention": attention_data(row)} if row else {})}


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


async def system_origin(
    session: AsyncSession, owner_id: str, agent_id: str | None, thread_id: str | None
) -> tuple[str, str, str | None]:
    """The owner's agent and conversation an item is about, checked for ownership.

    A work thread, or one that no longer exists, falls back to the agent's own
    conversation, as for every other notification; a missing agent falls back to the
    Personal Agent. Returns the group id when the origin is a group conversation.
    """
    from .personal_agent import ensure_personal_agent
    from .schema import AgentRow, ThreadRow
    from .threads import conversation_thread

    agent = await session.get(AgentRow, agent_id) if agent_id else None
    if agent is not None and agent.owner_id == owner_id:
        thread = await session.get(ThreadRow, thread_id) if thread_id else None
        if (
            thread is not None
            and thread.owner_id == owner_id
            and thread.purpose == "conversation"
            and thread.agent_id in {agent.id, None}
        ):
            return agent.id, thread.id, thread.group_id
        return agent.id, (await conversation_thread(session, owner_id, agent.id)).id, None
    personal = await ensure_personal_agent(session, owner_id)
    return personal.id, (await conversation_thread(session, owner_id, personal.id)).id, None


def system_coalesce_key(owner_id: str, code: str, group: str) -> str:
    return request_hash({"system_group": [owner_id, code, group]})


async def raise_system_attention(
    session: AsyncSession,
    owner_id: str,
    code: str,
    subject: str,
    parameters: dict[str, Any] | None = None,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    group: str | None = None,
    importance: str | None = None,
) -> AttentionRow | None:
    """One owner-visible item per (code, subject), straight to ready.

    It does not depend on the event projection loop, so the watchdog can still reach
    the owner while that loop is the thing that is stalled. Raising the same subject
    again is a no-op, including after the owner has seen it. The item opens the agent
    and conversation it is about (``agent_id``/``thread_id``), or the Personal Agent's
    when it concerns no agent or that agent is gone. With ``group``, a further item of
    the same group joins the one still open (its ``count`` grows) instead of adding one.
    ``importance`` is given only to deliver a classified notification whose own
    projection kept failing, so a critical alert is never lost.
    """
    importance = importance or SYSTEM_ATTENTION[code]
    logical = request_hash({"system": [owner_id, code, subject]})
    if await session.scalar(
        select(AttentionRow.id).where(
            AttentionRow.owner_id == owner_id, AttentionRow.logical_key == logical
        )
    ):
        return None
    if group is not None:
        open_row = await session.scalar(
            select(AttentionRow)
            .where(
                AttentionRow.owner_id == owner_id,
                AttentionRow.coalesce_key == system_coalesce_key(owner_id, code, group),
                AttentionRow.status.in_(["pending", "ready"]),
            )
            .order_by(AttentionRow.created_at)
            .limit(1)
            .with_for_update()
        )
        if open_row is not None:
            open_row.parameters = {
                **open_row.parameters,
                **(parameters or {}),
                "count": int(open_row.parameters.get("count", 1)) + 1,
                "execution_authorized": False,
            }
            open_row.source_count += 1
            open_row.version, open_row.updated_at = open_row.version + 1, utcnow()
            emit(
                session,
                owner_id,
                "attention.updated",
                agent_id=open_row.agent_id,
                thread_id=open_row.thread_id,
                payload=attention_data(open_row),
            )
            return None
    origin_agent, origin_thread, group_id = await system_origin(
        session, owner_id, agent_id, thread_id
    )
    now = utcnow()
    row = AttentionRow(
        id=stable_id(owner_id, "attention:" + logical),
        owner_id=owner_id,
        agent_id=origin_agent,
        thread_id=origin_thread,
        logical_key=logical,
        coalesce_key=system_coalesce_key(owner_id, code, group)
        if group is not None
        else request_hash({"scope": [owner_id, origin_agent, "system:" + code, subject]}),
        importance=importance,
        code=code,
        parameters={
            **(parameters or {}),
            **({"group_id": group_id} if group_id else {}),
            **({"count": 1} if group is not None else {}),
            "execution_authorized": False,
        },
        status="ready",
        source_events=[],
        source_count=1,
        version=1,
        due_at=now,
    )
    session.add(row)
    await session.flush()
    for kind in ("attention.updated", "attention.ready"):
        emit(
            session,
            owner_id,
            kind,
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload=attention_data(row),
        )
    return row


async def settle_system_attention(
    session: AsyncSession, owner_id: str, code: str, subject: str
) -> bool:
    """Withdraw an unread system item once its condition has cleared, so it never
    keeps claiming a state that is no longer true."""
    logical = request_hash({"system": [owner_id, code, subject]})
    row = await session.scalar(
        select(AttentionRow)
        .where(AttentionRow.owner_id == owner_id, AttentionRow.logical_key == logical)
        .with_for_update()
    )
    if row is None:
        return False
    return withdraw_attention(session, row)


def withdraw_attention(session: AsyncSession, row: AttentionRow) -> bool:
    """Suppress an unread item whose state is no longer true."""
    if row.status not in {"pending", "ready"}:
        return False
    row.status, row.version, row.updated_at = "suppressed", row.version + 1, utcnow()
    row.parameters = {**row.parameters, "suppression_code": "attention_superseded_state"}
    emit(
        session,
        row.owner_id,
        "attention.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=attention_data(row),
    )
    return True
