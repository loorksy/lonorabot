"""Opportunity identity and immutable transition history reuse the existing event ledger."""

import json
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.opportunity import OpportunityCreate
from lonora_core.chart_controller import validate_timeframe
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import assert_payload_binding
from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import EventRow, GroupRow, MarketWatchRow, TradingOpportunityRow
from .trading_decisions import read_decision
from .transactions import owned_agent, owned_thread, resource_data

TERMINAL = {"invalidated", "expired", "completed"}


async def owned_opportunity(
    session: AsyncSession, owner_id: str, identifier: str, *, lock: bool = False
) -> TradingOpportunityRow:
    query = select(TradingOpportunityRow).where(
        TradingOpportunityRow.owner_id == owner_id, TradingOpportunityRow.id == identifier
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(query)
    if row is None:
        raise LonoraError("opportunity_not_found", 404)
    return row


def opportunity_data(row: TradingOpportunityRow) -> dict[str, Any]:
    return {
        **resource_data(row),
        "account_id": row.account_id,
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "setup_key": row.setup_key,
        "status": row.status,
        "expires_at": row.expires_at.isoformat(),
        "last_validated_at": row.last_validated_at.isoformat() if row.last_validated_at else None,
    }


def transition(
    session: AsyncSession,
    row: TradingOpportunityRow,
    status: str,
    reason_code: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> None:
    previous = row.status
    row.status, row.updated_at, row.version = status, utcnow(), row.version + 1
    row.state = {**row.state, "reason_code": reason_code}
    # A full typed definition/version and evidence references are frozen here.
    emit(
        session,
        row.owner_id,
        "opportunity.transition",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload={
            "id": row.id,
            "previous_status": previous,
            "status": status,
            "reason_code": reason_code,
            "version": row.version,
            "account_id": row.account_id,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "definition": row.payload,
            "evidence": evidence or {},
        },
    )


async def create_opportunity(
    session: AsyncSession, owner_id: str, agent_id: str, thread_id: str, body: OpportunityCreate
) -> TradingOpportunityRow:
    await validate_references(
        session,
        owner_id,
        body.account_id,
        body.symbol,
        body.timeframe,
        body.supporting_decision_ids + body.contradicting_decision_ids,
    )
    agent = await owned_agent(session, owner_id, agent_id)
    assert_payload_binding(agent, body.model_dump(mode="json"))
    thread = await owned_thread(session, owner_id, thread_id, lock=True)
    if thread.agent_id and thread.agent_id != agent_id:
        raise LonoraError("agent_thread_mismatch", 409)
    if thread.group_id:
        group = await session.get(GroupRow, thread.group_id)
        if (
            group is None
            or group.owner_id != owner_id
            or agent_id not in group.payload.get("member_ids", [])
        ):
            raise LonoraError("agent_not_group_member", 409)
    await BrokerSessionRepository().get(session, owner_id, body.account_id)
    if body.watch_id:
        watch = await session.get(MarketWatchRow, body.watch_id)
        if (
            watch is None
            or watch.owner_id != owner_id
            or watch.agent_id != agent_id
            or watch.payload.get("account_id") != body.account_id
            or watch.payload.get("symbol") != body.symbol
            or watch.payload.get("timeframe") != body.timeframe
        ):
            raise LonoraError("opportunity_watch_scope_mismatch", 409)
    identity = stable_id(
        agent_id,
        json.dumps(
            [body.account_id, body.symbol, body.timeframe, body.setup_key],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    row = await session.get(TradingOpportunityRow, identity, with_for_update=True)
    if row:
        return row  # Same scoped setup across wakes; updates require its current version.
    if body.definition.expires_at <= utcnow():
        raise LonoraError("thesis_expiry_invalid", 422)
    row = TradingOpportunityRow(
        id=identity,
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        account_id=body.account_id,
        symbol=body.symbol,
        timeframe=body.timeframe,
        setup_key=body.setup_key,
        status="forming",
        expires_at=body.definition.expires_at,
        payload=body.model_dump(mode="json"),
        state={},
    )
    session.add(row)
    await session.flush()
    transition(session, row, "forming", "opportunity_detected")
    return row


async def opportunity_history(
    session: AsyncSession, owner_id: str, identifier: str
) -> list[dict[str, Any]]:
    await owned_opportunity(session, owner_id, identifier)
    events = await session.scalars(
        select(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.kind == "opportunity.transition",
            EventRow.payload["id"].as_string() == identifier,
        )
        .order_by(EventRow.cursor.desc())
        .limit(30)
    )
    return [
        {
            "observed_at": row.created_at.isoformat(),
            **{key: value for key, value in row.payload.items() if not key.startswith("_ln_")},
        }
        for row in events
    ]


async def validate_references(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    symbol: str,
    timeframe: str,
    identifiers: list[str],
) -> None:
    validate_timeframe(timeframe)
    for identifier in identifiers:
        decision = await read_decision(session, owner_id, identifier)
        if (decision.account_id, decision.symbol, decision.timeframe) != (
            account_id,
            symbol,
            timeframe,
        ):
            raise LonoraError("thesis_evidence_scope_mismatch", 409)


def opportunity_summary(row: TradingOpportunityRow) -> dict[str, Any]:
    data = opportunity_data(row)
    data.pop("payload")
    data.pop("state")
    return {
        **data,
        "direction": row.payload["definition"]["direction"],
        "reason_code": row.state.get("reason_code"),
    }
