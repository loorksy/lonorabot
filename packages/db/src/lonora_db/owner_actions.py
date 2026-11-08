"""Owner action cards: durable, single-use owner actions shown inside the conversation.

A card stores the exact effect it performs (``payload``, hashed) and the record it acts
on (``subject``). Agents propose cards through a tool and the runtime raises some from
events (a new restriction, an operation that became uncertain); only the owner's session
confirms one, through the existing owner function for that effect (see the owner
actions API route). Everything the owner sees on a card is derived here from the records
it names, at read time: never model text, never the restriction reason an agent wrote.

A card is pending until it is confirmed, cancelled, superseded (its record changed, or
another card did the same thing) or expired. Expiry needs no scheduler: a pending card
past ``expires_at`` reads as expired and is settled as expired when next touched.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_contracts.risk_limits import MonetaryRiskLimits
from lonora_contracts.trading import UNRESOLVED_STATUSES, TradingControl
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash, stable_id
from pydantic import ValidationError
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import (
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    OwnerActionRow,
    ThreadRow,
    TradingJournalRow,
    TradingRestrictionRow,
)
from .trading_readiness import RISK_LIMIT_NAMES, global_trading, risk_limit_frame
from .trading_restrictions import restriction_state
from .transactions import SettingsRepository, execution_policy_key, owned_thread

# How long a card stays usable. A lift card never outlives its restriction.
LIFETIME = {
    "resume_trading": timedelta(hours=24),
    "lift_restriction": timedelta(days=31),
    "resolve_operation": timedelta(days=7),
    "set_account_limits": timedelta(hours=24),
    # An agent's proposal to create an agent, and the Undo card after a creation.
    "create_agent": timedelta(hours=24),
    "agent_created": timedelta(days=7),
}
# Pending cards one agent may have proposed at once; runtime cards do not count.
MAXIMUM_PENDING_PER_AGENT = 5
UPPER_LIMITS = (
    "max_trade_risk",
    "max_trade_risk_equity_percent",
    "max_daily_loss",
    "max_open_risk",
    "max_open_risk_equity_percent",
)
# Every field a limits card can change, in the order its lines show them. A card shows a
# line for each one that differs, so it never signs an effect the owner did not see.
LIMIT_CHANGE_NAMES = ("currency", *RISK_LIMIT_NAMES, "trading_day_timezone")


def payload_hash(kind: str, payload: dict[str, Any]) -> str:
    return request_hash({"kind": kind, "payload": payload})


def live_status(row: OwnerActionRow, now: datetime | None = None) -> str:
    if row.status == "pending" and row.expires_at <= (now or utcnow()):
        return "expired"
    return row.status


def proposed_limits(current: MonetaryRiskLimits, payload: dict[str, Any]) -> MonetaryRiskLimits:
    """The account's limits after the card's exact changes; other limits stay as they are."""
    values = current.model_dump()
    values.update({name: Decimal(str(value)) for name, value in payload["set"].items()})
    values.update({name: None for name in payload["remove"]})
    for name in ("currency", "trading_day_timezone"):
        if payload.get(name) is not None:
            values[name] = payload[name]
    try:
        return MonetaryRiskLimits.model_validate(values)
    except ValidationError as error:
        raise LonoraError("owner_action_limits_invalid", 422) from error


def widens(current: MonetaryRiskLimits, proposed: MonetaryRiskLimits) -> bool:
    """Whether new limits admit more risk anywhere: raising or removing a ceiling, lowering
    or removing the free-margin floor, re-denominating set amounts or moving the day."""
    for name in UPPER_LIMITS:
        old, new = getattr(current, name), getattr(proposed, name)
        if old is not None and (new is None or new > old):
            return True
    floor, new_floor = current.min_free_margin, proposed.min_free_margin
    if floor is not None and (new_floor is None or new_floor < floor):
        return True
    amounts = any(
        getattr(current, name) is not None
        for name in ("max_trade_risk", "max_daily_loss", "max_open_risk", "min_free_margin")
    )
    if amounts and proposed.currency != current.currency:
        return True
    return (
        current.max_daily_loss is not None
        and proposed.trading_day_timezone != current.trading_day_timezone
    )


async def account_policy(session: AsyncSession, owner_id: str, account_id: str) -> ExecutionPolicy:
    return ExecutionPolicy.model_validate(
        await SettingsRepository().get(session, execution_policy_key(owner_id, account_id))
    )


async def owned_account(
    session: AsyncSession, owner_id: str, account_id: str, *, lock: bool = False
) -> BrokerSessionRow:
    row = await session.get(
        BrokerSessionRow, account_id, with_for_update=lock, populate_existing=lock
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("broker_session_not_found", 404)
    return row


def _mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def account_facts(row: BrokerSessionRow | None, account_id: str) -> dict[str, Any]:
    """The broker identity the owner recognizes; no connection secret or raw state."""
    label = None
    identity = _mapping(row.state.get("broker_identity")) if row else {}
    if row is not None and identity.get("connection_version") == row.version:
        parts: list[Any] = [identity.get(key) for key in ("broker", "login", "server")]
        label = " · ".join(str(part) for part in parts if isinstance(part, str) and part) or None
    return {
        "id": account_id,
        "label": label,
        "provider": row.payload.get("provider") if row else None,
    }


async def stale_reason(
    session: AsyncSession, owner_id: str, kind: str, payload: dict[str, Any]
) -> str | None:
    """Why the card's effect no longer applies to current state, or None if it does.

    Raises when the record it names is not the owner's: such a card is never created.
    """
    if kind == "resume_trading":
        return (
            "trading_already_running"
            if (await global_trading(session))["state"] == "running"
            else None
        )
    if kind == "lift_restriction":
        restriction = await session.get(TradingRestrictionRow, payload["restriction_id"])
        if restriction is None or restriction.owner_id != owner_id:
            raise LonoraError("restriction_not_found", 404)
        return (
            "restriction_already_ended"
            if restriction_state(restriction) in {"revoked", "expired"}
            else None
        )
    if kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, payload["operation_id"])
        if (
            operation is None
            or operation.owner_id != owner_id
            or (operation.execution_mode != "live")
        ):
            raise LonoraError("operation_not_found", 404)
        return None if operation.status == "ambiguous" else "operation_already_settled"
    if kind == "set_account_limits":
        await owned_account(session, owner_id, payload["account_id"])
        current = (await account_policy(session, owner_id, payload["account_id"])).risk
        return "limits_already_set" if proposed_limits(current, payload) == current else None
    if kind == "create_agent":
        from .agent_creation import check_creation

        try:
            await check_creation(session, owner_id, payload["spec"])
        except LonoraError as error:
            return CREATION_STALE.get(error.code, "agent_creation_unavailable")
        return None
    if kind == "agent_created":
        agent = await session.get(AgentRow, payload["agent_id"])
        return "agent_already_removed" if agent is None or agent.owner_id != owner_id else None
    raise LonoraError("owner_action_kind_unsupported", 422)


# Why a creation card no longer applies, by the refusal its re-check raised.
CREATION_STALE = {
    "agent_limit_reached": "agent_limit_reached",
    "agent_not_found": "agent_report_to_missing",
    "agent_report_to_invalid": "agent_report_to_missing",
    "broker_sessions_not_found": "broker_connection_changed",
    "broker_connection_changed": "broker_connection_changed",
}


def proposal_payload(proposal: OwnerActionProposal) -> tuple[str, dict[str, Any]]:
    """The card's exact stored effect and the record it acts on."""
    if proposal.kind == "resume_trading":
        return "trading", TradingControl(enabled=True, emergency_stop=False).model_dump()
    if proposal.kind == "lift_restriction":
        assert proposal.restriction_id is not None
        return "restriction:" + proposal.restriction_id, {"restriction_id": proposal.restriction_id}
    if proposal.kind == "resolve_operation":
        assert proposal.operation_id is not None
        return "operation:" + proposal.operation_id, {"operation_id": proposal.operation_id}
    assert proposal.account_id is not None
    return "account:" + proposal.account_id, {
        "account_id": proposal.account_id,
        "set": {name: str(value) for name, value in sorted(proposal.set_limits.items())},
        "remove": sorted(set(proposal.remove_limits)),
        "currency": proposal.currency,
        "trading_day_timezone": proposal.trading_day_timezone,
    }


async def agent_names(session: AsyncSession, owner_id: str, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = await session.scalars(
        select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.id.in_(sorted(ids)))
    )
    return {row.id: row.name for row in rows}


async def several_accounts(session: AsyncSession, owner_id: str) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(BrokerSessionRow)
        .where(BrokerSessionRow.owner_id == owner_id)
    )
    return (count or 0) > 1


def _execution_agent(row: TradingJournalRow) -> str | None:
    agent = _mapping(_mapping(row.result.get("details")).get("execution")).get("agent_id")
    return agent if isinstance(agent, str) else None


async def card_facts(
    session: AsyncSession, row: OwnerActionRow, now: datetime
) -> tuple[dict[str, Any], bool]:
    """Server facts the card shows, read now from the records it names; and whether the
    owner's confirmation needs a passkey (widening money limits)."""
    owner_id, payload = row.owner_id, row.payload
    facts: dict[str, Any] = {"several_accounts": await several_accounts(session, owner_id)}
    if row.kind == "resume_trading":
        facts["global_trading"] = await global_trading(session)
        return facts, False
    if row.kind == "lift_restriction":
        restriction = await session.get(TradingRestrictionRow, payload["restriction_id"])
        if restriction is None:
            return facts, False
        names = await agent_names(
            session,
            owner_id,
            {value for value in (restriction.agent_id, restriction.created_by_agent_id) if value},
        )
        facts["account"] = account_facts(
            await session.get(BrokerSessionRow, restriction.account_id), restriction.account_id
        )
        facts["restriction"] = {
            "action_class": restriction.action_class,
            "symbol": restriction.symbol,
            "all_agents": restriction.agent_id is None,
            "agent_name": names.get(restriction.agent_id or ""),
            "includes_owner_manual": restriction.applies_to_owner_manual,
            "state": restriction_state(restriction, now),
            "valid_from": restriction.valid_from.isoformat(),
            "valid_until": restriction.valid_until.isoformat() if restriction.valid_until else None,
            # Who set it, never the reason text: an agent's reason is model prose.
            "source": restriction.source,
            "set_by_agent_name": names.get(restriction.created_by_agent_id or ""),
        }
        return facts, False
    if row.kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, payload["operation_id"])
        if operation is None:
            return facts, False
        request = operation.request
        producer = _execution_agent(operation)
        names = await agent_names(session, owner_id, {producer} if producer else set())
        facts["account"] = account_facts(
            await session.get(BrokerSessionRow, operation.account_id), operation.account_id
        )
        facts["operation"] = {
            "action": request.get("action"),
            "symbol": request.get("symbol"),
            "volume": None if request.get("volume") is None else str(request["volume"]),
            "price": None if request.get("price") is None else str(request["price"]),
            "has_ticket": bool(request.get("position_id") or request.get("order_id")),
            "status": operation.status,
            "submitted_at": operation.submitted_at.isoformat() if operation.submitted_at else None,
            "by_agent_name": names.get(producer or ""),
            "by_owner": producer is None,
        }
        facts["blocks"] = "new_risk_on_this_symbol_or_ticket"
        return facts, False
    if row.kind in {"create_agent", "agent_created"}:
        return await creation_facts(session, row, facts), False
    account_id = payload["account_id"]
    facts["account"] = account_facts(await session.get(BrokerSessionRow, account_id), account_id)
    current = (await account_policy(session, owner_id, account_id)).risk
    facts["current"] = risk_limit_frame(account_id, ExecutionPolicy(risk=current))
    try:
        proposed = proposed_limits(current, payload)
    except LonoraError:
        # The limits changed since the card was raised and its change no longer fits
        # them: confirming only settles it, so no passkey ceremony is asked for.
        facts["no_longer_applies"] = True
        return facts, False
    facts["proposed"] = risk_limit_frame(account_id, ExecutionPolicy(risk=proposed))
    facts["changes"] = limit_changes(current, proposed)
    return facts, widens(current, proposed)


async def creation_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    """What a creation card shows: the agent's name, template, focus pair and ladder,
    and whom it reports to. The responsibility text (model prose) is never shown."""
    from lonora_contracts.agent_creation import TEMPLATE_LEVEL

    from .agent_creation import agent_origin, report_targets, undo_plan
    from .agent_permissions import effective_permission

    owner_id = row.owner_id
    if row.kind == "create_agent":
        spec = row.payload["spec"]
        report_to = [str(item) for item in spec.get("report_to", [])]
        names = await agent_names(session, owner_id, set(report_to))
        account_id = spec.get("account_id")
        if account_id:
            facts["account"] = account_facts(
                await session.get(BrokerSessionRow, account_id), account_id
            )
        model = spec.get("model")
        facts["agent"] = {
            "exists": False,
            "name": spec["name"],
            "template": spec["template"],
            "symbol": spec.get("symbol"),
            "level": TEMPLATE_LEVEL[spec["template"]],
            "paused": False,
            "report_to": [names[item] for item in report_to if item in names],
            "model": cast(dict[str, Any], model).get("model") if isinstance(model, dict) else None,
        }
        return facts
    agent_id = row.payload["agent_id"]
    agent = await session.get(AgentRow, agent_id)
    if agent is None or agent.owner_id != owner_id:
        facts["agent"] = {"exists": False, "name": row.result.get("agent_name")}
        return facts
    origin = await agent_origin(session, owner_id, agent_id)
    report_to = report_targets(origin)
    names = await agent_names(session, owner_id, set(report_to))
    if agent.trading_account_id:
        facts["account"] = account_facts(
            await session.get(BrokerSessionRow, agent.trading_account_id),
            agent.trading_account_id,
        )
    facts["agent"] = {
        "exists": True,
        "name": agent.name,
        "template": origin.get("template"),
        "symbol": agent.trading_symbol,
        "level": await effective_permission(session, owner_id, agent_id),
        "paused": agent.paused,
        "report_to": [names[item] for item in report_to if item in names],
        "model": None,
    }
    facts["undo"] = await undo_plan(session, owner_id, agent_id)
    return facts


def limit_changes(
    current: MonetaryRiskLimits, proposed: MonetaryRiskLimits
) -> list[dict[str, Any]]:
    """One line per changed field: limits, their currency and the trading-day zone."""
    return [
        {
            "name": name,
            "from": None if getattr(current, name) is None else str(getattr(current, name)),
            "to": None if getattr(proposed, name) is None else str(getattr(proposed, name)),
        }
        for name in LIMIT_CHANGE_NAMES
        if getattr(current, name) != getattr(proposed, name)
    ]


async def owner_action_data(
    session: AsyncSession, row: OwnerActionRow, now: datetime | None = None
) -> dict[str, Any]:
    moment = now or utcnow()
    facts, passkey = await card_facts(session, row, moment)
    status = live_status(row, moment)
    return {
        "id": row.id,
        "kind": row.kind,
        "status": status,
        "status_reason": "expired"
        if status == "expired" and row.status == "pending"
        else (row.status_reason),
        "source": row.source,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "run_id": row.run_id,
        "timeline_seq": row.timeline_seq,
        "facts": facts,
        "requires_passkey": passkey,
        "result": row.result,
        "expires_at": row.expires_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_via": row.decided_via,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def owner_action_event(session: AsyncSession, row: OwnerActionRow) -> None:
    emit(
        session,
        row.owner_id,
        "owner_action.updated",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.run_id,
        payload={
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "status_reason": row.status_reason,
            "thread_id": row.thread_id,
            "transition_id": row.id + ":" + row.status,
        },
    )


async def settle(
    session: AsyncSession,
    row: OwnerActionRow,
    status: str,
    reason: str | None,
    *,
    via: str | None = None,
    result: dict[str, Any] | None = None,
) -> OwnerActionRow:
    now = utcnow()
    row.status, row.status_reason, row.updated_at = status, reason, now
    if status in {"confirmed", "cancelled"}:
        row.decided_at, row.decided_via = now, via
    if result is not None:
        row.result = result
    await session.flush()
    await owner_action_event(session, row)
    return row


async def lock_owner_actions(session: AsyncSession, owner_id: str) -> None:
    """Serialize card creation and settlement per owner (dedupe, cap, subject supersede)."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "owner-actions:" + owner_id},
        )


async def supersede_subject(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    subject: str,
    reason: str,
    *,
    keep: str | None = None,
    effect: str | None = None,
) -> list[OwnerActionRow]:
    """Settle every other pending card for the same record: its effect is done or gone.

    ``effect`` narrows it to cards with that exact payload hash (the same change proposed
    twice); a different change to the same account's limits stays on its card.
    """
    query = select(OwnerActionRow).where(
        OwnerActionRow.owner_id == owner_id,
        OwnerActionRow.kind == kind,
        OwnerActionRow.subject == subject,
        OwnerActionRow.status == "pending",
    )
    if effect is not None:
        query = query.where(OwnerActionRow.payload_hash == effect)
    rows = list(
        await session.scalars(
            query.order_by(OwnerActionRow.created_at, OwnerActionRow.id).with_for_update()
        )
    )
    settled: list[OwnerActionRow] = []
    for row in rows:
        if row.id == keep:
            continue
        expired = row.expires_at <= utcnow()
        settled.append(await settle(session, row, "expired" if expired else "superseded", reason))
    return settled


async def card_thread(
    session: AsyncSession, owner_id: str, agent_id: str, thread_id: str | None
) -> ThreadRow:
    """The owner's conversation that shows the card: the given one when it is a
    conversation, otherwise the agent's own conversation."""
    from .threads import conversation_thread

    thread = await session.get(ThreadRow, thread_id) if thread_id else None
    if (
        thread is None
        or thread.owner_id != owner_id
        or thread.purpose != "conversation"
        or (thread.agent_id not in {agent_id, None})
    ):
        thread = await conversation_thread(session, owner_id, agent_id)
    return await owned_thread(session, owner_id, thread.id, lock=True)


def expiry(kind: str, payload_expires: datetime | None, now: datetime) -> datetime:
    limit = now + LIFETIME[kind]
    return min(limit, payload_expires) if payload_expires is not None else limit


async def subject_expiry(
    session: AsyncSession, kind: str, payload: dict[str, Any]
) -> datetime | None:
    if kind == "lift_restriction":
        restriction = await session.get(TradingRestrictionRow, payload["restriction_id"])
        return restriction.valid_until if restriction else None
    return None


async def create_card(
    session: AsyncSession,
    owner_id: str,
    *,
    card_id: str,
    agent_id: str,
    thread: ThreadRow,
    run_id: str | None,
    source: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
) -> OwnerActionRow:
    now = utcnow()
    row = OwnerActionRow(
        id=card_id,
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread.id,
        run_id=run_id,
        source=source,
        kind=kind,
        subject=subject,
        payload=payload,
        payload_hash=payload_hash(kind, payload),
        status="pending",
        result={},
        # The card sits after everything already in the conversation, like an approval.
        timeline_seq=thread.next_seq,
        expires_at=expiry(kind, await subject_expiry(session, kind, payload), now),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    await owner_action_event(session, row)
    return row


async def pending_effect(
    session: AsyncSession, agent_id: str, kind: str, digest: str
) -> OwnerActionRow | None:
    return await session.scalar(
        select(OwnerActionRow)
        .where(
            OwnerActionRow.agent_id == agent_id,
            OwnerActionRow.kind == kind,
            OwnerActionRow.payload_hash == digest,
            OwnerActionRow.status == "pending",
        )
        .with_for_update()
    )


async def propose(
    session: AsyncSession,
    owner_id: str,
    proposal: OwnerActionProposal,
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """An agent's card: validated against current state, deduplicated, capped.

    Returns the card and whether it is new. A repeated proposal of the same effect by
    the same agent returns the pending card it already raised.
    """
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    subject, payload = proposal_payload(proposal)
    return await propose_effect(
        session,
        owner_id,
        proposal.kind,
        subject,
        payload,
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def propose_effect(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """An agent's card for one validated effect: deduplicated per agent, capped. The
    caller holds the owner-actions lock and has checked the card id is new."""
    reason = await stale_reason(session, owner_id, kind, payload)
    if reason is not None:
        raise LonoraError("owner_action_not_needed_" + reason, 409)
    current = await pending_effect(session, agent_id, kind, payload_hash(kind, payload))
    if current is not None:
        if current.thread_id is not None and current.expires_at > utcnow():
            return current, False
        # An expired card, or one whose conversation was deleted, gives way to a new one.
        await settle(
            session,
            current,
            "expired" if current.expires_at <= utcnow() else "superseded",
            "expired" if current.expires_at <= utcnow() else "conversation_deleted",
        )
    pending = await session.scalar(
        select(func.count())
        .select_from(OwnerActionRow)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.agent_id == agent_id,
            OwnerActionRow.source == "agent",
            OwnerActionRow.status == "pending",
            OwnerActionRow.expires_at > utcnow(),
        )
    )
    if (pending or 0) >= MAXIMUM_PENDING_PER_AGENT:
        raise LonoraError("owner_action_limit", 429)
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="agent",
        kind=kind,
        subject=subject,
        payload=payload,
    )
    return row, True


async def propose_creation(
    session: AsyncSession,
    owner_id: str,
    spec: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """A creation card when no owner message asked for the agent: the owner's tap
    creates it. A repeated proposal of the same agent returns the card shown."""
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    return await propose_effect(
        session,
        owner_id,
        "create_agent",
        "agent-create",
        {"spec": spec},
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def raise_created_card(
    session: AsyncSession,
    owner_id: str,
    created_agent: AgentRow,
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow:
    """The one-line result card of a creation, with Undo; one per created agent."""
    await lock_owner_actions(session, owner_id)
    subject = "agent:" + created_agent.id
    card_id = stable_id(owner_id, "owner-action:agent_created:" + subject)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="agent_created",
        subject=subject,
        payload={"agent_id": created_agent.id},
    )
    row.result = {"agent_name": created_agent.name}
    return row


async def raise_system_card(
    session: AsyncSession,
    owner_id: str,
    proposal: OwnerActionProposal,
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """A card raised from a runtime event, with no model involved; one per record.

    The id is derived from the record, so replaying the event never adds a second card,
    and an effect that no longer applies raises none.
    """
    await lock_owner_actions(session, owner_id)
    subject, payload = proposal_payload(proposal)
    card_id = stable_id(owner_id, "owner-action:" + proposal.kind + ":" + subject)
    if await session.get(OwnerActionRow, card_id) is not None:
        return None
    if await stale_reason(session, owner_id, proposal.kind, payload) is not None:
        return None
    if await pending_effect(session, agent_id, proposal.kind, payload_hash(proposal.kind, payload)):
        return None
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind=proposal.kind,
        subject=subject,
        payload=payload,
    )


async def owned_card(
    session: AsyncSession, owner_id: str, card_id: str, *, lock: bool = False
) -> OwnerActionRow:
    row = await session.get(OwnerActionRow, card_id, with_for_update=lock, populate_existing=lock)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("owner_action_not_found", 404)
    return row


async def thread_cards(
    session: AsyncSession, owner_id: str, thread_id: str, limit: int = 50
) -> list[OwnerActionRow]:
    rows = await session.scalars(
        select(OwnerActionRow)
        .where(OwnerActionRow.owner_id == owner_id, OwnerActionRow.thread_id == thread_id)
        .order_by(OwnerActionRow.created_at.desc(), OwnerActionRow.id)
        .limit(limit)
    )
    return list(reversed(list(rows)))


def confirmation_code(row: OwnerActionRow) -> str:
    if row.kind == "resolve_operation":
        return "owner_action_resolve_" + str(row.result.get("outcome", "unknown"))
    if row.kind == "agent_created":
        return "owner_action_undo_" + str(row.result.get("undo", "paused"))
    return "owner_action_" + row.kind


def _same_symbol(left: str | None, right: str | None) -> bool:
    return left is None or right is None or left.casefold() == right.casefold()


async def still_holding(session: AsyncSession, row: OwnerActionRow) -> list[str]:
    """What still holds new risk where a lift or an answer just released it, read after
    the effect: Stop new trading, another pause in force over the same market and agents,
    or another trade there without a confirmed broker outcome. One fixed clause each."""
    if row.kind not in {"lift_restriction", "resolve_operation"}:
        return []
    agent: str | None = None
    lifted_id = answered_id = ""
    tickets: list[str] = []
    if row.kind == "lift_restriction":
        lifted = await session.get(TradingRestrictionRow, row.payload["restriction_id"])
        if lifted is None:
            return []
        account, symbol, agent, lifted_id = (
            lifted.account_id,
            lifted.symbol,
            lifted.agent_id,
            lifted.id,
        )
    else:
        operation = await session.get(TradingJournalRow, row.payload["operation_id"])
        if operation is None:
            return []
        account, answered_id = operation.account_id, operation.operation_id
        symbol = cast(str | None, operation.request.get("symbol"))
        tickets = [
            str(operation.request[key])
            for key in ("position_id", "order_id")
            if operation.request.get(key)
        ]
    notes: list[str] = []
    if (await global_trading(session))["state"] == "stopped":
        notes.append("owner_action_still_stopped")
    now = utcnow()
    pauses = await session.scalars(
        select(TradingRestrictionRow).where(
            TradingRestrictionRow.owner_id == row.owner_id,
            TradingRestrictionRow.account_id == account,
            TradingRestrictionRow.revoked_at.is_(None),
            TradingRestrictionRow.valid_from <= now,
            TradingRestrictionRow.id != lifted_id,
        )
    )
    if any(
        (pause.valid_until is None or pause.valid_until > now)
        and _same_symbol(pause.symbol, symbol)
        and (pause.agent_id is None or agent is None or pause.agent_id == agent)
        for pause in pauses
    ):
        notes.append("owner_action_still_paused")
    scope: list[ColumnElement[bool]] = []
    if symbol is not None:
        scope.append(func.lower(TradingJournalRow.request["symbol"].as_string()) == symbol.lower())
    scope.extend(
        TradingJournalRow.request[key].as_string() == ticket
        for key in ("position_id", "order_id")
        for ticket in tickets
    )
    unresolved = select(TradingJournalRow.operation_id).where(
        TradingJournalRow.owner_id == row.owner_id,
        TradingJournalRow.account_id == account,
        TradingJournalRow.execution_mode == "live",
        TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
        TradingJournalRow.operation_id != answered_id,
    )
    if scope:
        unresolved = unresolved.where(or_(*scope))
    if await session.scalar(unresolved.limit(1)) is not None:
        notes.append("owner_action_still_unresolved")
    if row.kind == "lift_restriction" and not notes:
        notes.append("owner_action_admitted_again")
    return notes


async def confirmation_agent(session: AsyncSession, row: OwnerActionRow) -> str | None:
    """Who speaks the confirmation: the card's agent while it exists (held against a
    concurrent delete), otherwise Lonora."""
    present = await session.scalar(
        select(AgentRow.id)
        .where(AgentRow.id == row.agent_id, AgentRow.owner_id == row.owner_id)
        .with_for_update(key_share=True)
    )
    if present is not None:
        return present
    return await session.scalar(
        select(AgentRow.id).where(AgentRow.owner_id == row.owner_id, AgentRow.role == "personal")
    )


async def confirm_in_thread(session: AsyncSession, row: OwnerActionRow) -> None:
    """One server-written line in the card's conversation saying what changed, and what
    still holds new risk there (``still_holding``), read after the effect.

    The clauses are fixed texts in the conversation's language; posting is idempotent
    per card, and a card whose conversation is gone posts nothing.
    """
    from lonora_bus.attention import attention_text

    from .conversation_locale import conversation_locale
    from .messages import message_data
    from .schema import EffectReceiptRow, MessageRow

    if row.status != "confirmed" or row.thread_id is None:
        return
    key = "owner-action-ack:" + row.id
    if await session.get(EffectReceiptRow, key):
        return
    # The agent before its conversation: the order a delete of that agent locks them in.
    speaker = await confirmation_agent(session, row)
    thread = await session.get(
        ThreadRow, row.thread_id, with_for_update=True, populate_existing=True
    )
    if thread is None or thread.owner_id != row.owner_id:
        return  # Deleted while the owner tapped: the effect stands, nothing to post in.
    locale = await conversation_locale(session, row.owner_id, thread.id)
    codes = [confirmation_code(row), *await still_holding(session, row)]
    message = MessageRow(
        id=stable_id(row.id, "owner-action-ack"),
        thread_id=thread.id,
        agent_id=speaker,
        seq=thread.next_seq,
        role="assistant",
        content=" ".join(attention_text(code, locale) for code in codes),
    )
    thread.next_seq += 1
    session.add(message)
    await session.flush()
    session.add(EffectReceiptRow(key=key, result={"message_id": message.id, "locale": locale}))
    emit(
        session,
        row.owner_id,
        "message.created",
        thread_id=thread.id,
        agent_id=message.agent_id,
        payload=message_data(message),
    )


async def awaiting_owner_answer(session: AsyncSession, owner_id: str, operation_id: str) -> bool:
    """The owner already has this uncertain operation in front of them: its resolve card
    waits for an answer, or its "operation_uncertain" item is still open. A later aging
    alert for the same operation would only repeat that fact."""
    card = await session.scalar(
        select(OwnerActionRow.id)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == "resolve_operation",
            OwnerActionRow.subject == "operation:" + operation_id,
            OwnerActionRow.status == "pending",
            OwnerActionRow.expires_at > utcnow(),
        )
        .limit(1)
    )
    if card is not None:
        return True
    item = await session.scalar(
        select(AttentionRow.id)
        .where(
            AttentionRow.owner_id == owner_id,
            AttentionRow.code == "operation_uncertain",
            AttentionRow.status.in_(["pending", "ready"]),
            AttentionRow.parameters["operation_id"].as_string() == operation_id,
        )
        .limit(1)
    )
    return item is not None


async def card_account(session: AsyncSession, row: OwnerActionRow) -> str | None:
    if row.kind == "set_account_limits":
        return cast(str, row.payload["account_id"])
    if row.kind == "create_agent":
        return cast(str | None, row.payload["spec"].get("account_id"))
    if row.kind == "lift_restriction":
        restriction = await session.get(TradingRestrictionRow, row.payload["restriction_id"])
        return restriction.account_id if restriction else None
    if row.kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, row.payload["operation_id"])
        return operation.account_id if operation else None
    return None


async def settle_for_delete(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Pending cards of a deleted agent or conversation, or about a deleted account, no
    longer apply: they are superseded with the reason, never left waiting to expire.

    A card the owner is deciding at this moment is skipped (its decision finishes on its
    own and posts nothing in a conversation that is gone), so the delete never waits on
    or deadlocks with a tap.
    """
    query = select(OwnerActionRow).where(
        OwnerActionRow.owner_id == owner_id, OwnerActionRow.status == "pending"
    )
    if agent_id is not None:
        query = query.where(OwnerActionRow.agent_id == agent_id)
    if thread_id is not None:
        query = query.where(OwnerActionRow.thread_id == thread_id)
    rows = list(
        await session.scalars(
            query.order_by(OwnerActionRow.created_at, OwnerActionRow.id).with_for_update(
                skip_locked=True
            )
        )
    )
    reason = (
        "agent_deleted"
        if agent_id is not None
        else "conversation_deleted"
        if thread_id is not None
        else "account_deleted"
    )
    for row in rows:
        if account_id is not None and await card_account(session, row) != account_id:
            continue
        await settle(session, row, "superseded", reason)
