"""Shared thesis lifecycle and final execution linkage, without another scheduler."""

from datetime import datetime
from typing import Any

from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.opportunity import OpportunityUpdate, ThesisDefinition
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.runs import create_run
from lonora_db.schema import (
    AgentRow,
    EffectReceiptRow,
    MarketWatchRow,
    TradingJournalRow,
    TradingOpportunityRow,
)
from lonora_db.threads import create_thread
from lonora_db.trading_decisions import read_decision
from lonora_db.trading_opportunities import (
    TERMINAL,
    owned_opportunity,
    transition,
    validate_references,
)
from lonora_market.health import assess_candles, assess_quote, timeframe_age_seconds
from lonora_market.relationships import relationship_usable
from lonora_session.idempotency import stable_id
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

ENTRY_ACTIONS = {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}


async def evidence_state(
    session: AsyncSession, row: TradingOpportunityRow, now: datetime
) -> tuple[list[str], dict[str, Any]]:
    definition = ThesisDefinition.model_validate(row.payload["definition"])
    codes: list[str] = []
    facts: dict[str, Any] = {
        "supporting": [],
        "contradicting": [],
        "health_assessments": [],
        "validated_at": now.isoformat(),
    }
    if now >= row.expires_at:
        codes.append("thesis_expired")
    if definition.decay_at and now >= definition.decay_at:
        codes.append("thesis_decay_horizon")
    if not row.payload.get("supporting_decision_ids"):
        codes.append("thesis_evidence_required")
    for name in ("supporting_decision_ids", "contradicting_decision_ids"):
        for identifier in row.payload.get(name, []):
            decision = await read_decision(session, row.owner_id, identifier)
            if (decision.account_id, decision.symbol, decision.timeframe) != (
                row.account_id,
                row.symbol,
                row.timeframe,
            ):
                raise LonoraError("thesis_evidence_scope_mismatch", 409)
            facts["supporting" if name.startswith("supporting") else "contradicting"].append(
                {
                    "id": decision.id,
                    "agent_id": decision.agent_id,
                    "action": decision.action,
                    "recorded_at": decision.recorded_at.isoformat(),
                    "logic_version": decision.logic_version,
                }
            )
            if name.startswith("contradicting"):
                codes.append("thesis_contradicting_evidence")
                continue
            if decision.action != definition.direction or decision.action == "WAIT":
                codes.append("thesis_direction_unconfirmed")
            quote = assess_quote(
                decision.evidence.quote,
                account_id=row.account_id,
                symbol=row.symbol,
                now=now,
                maximum_age_seconds=30,
            )
            candles = assess_candles(
                decision.evidence.candles,
                account_id=row.account_id,
                symbol=row.symbol,
                timeframe=row.timeframe,
                now=now,
                maximum_age_seconds=timeframe_age_seconds(row.timeframe),
            )
            facts["health_assessments"].extend(h.model_dump(mode="json") for h in (quote, candles))
            codes.extend(h.reason_code for h in (quote, candles) if not h.healthy)
            codes.extend(decision.gate_codes)
            for relationship in decision.evidence.relationships:
                facts.setdefault("relationships", []).append(
                    {
                        "id": relationship.id,
                        "state": relationship.state,
                        "valid_until": relationship.valid_until.isoformat()
                        if relationship.valid_until
                        else None,
                    }
                )
                if not relationship_usable(relationship, now):
                    codes.append("relationship_evidence_unreliable")
    watch_id = row.payload.get("watch_id")
    if watch_id:
        watch = await session.get(MarketWatchRow, watch_id)
        if watch is None or watch.owner_id != row.owner_id:
            codes.append("thesis_watch_unavailable")
        else:
            lifecycle = watch.state.get("lifecycle")
            valid_until = watch.state.get("confirmation_valid_until")
            if lifecycle == "invalidated":
                codes.append("thesis_watch_invalidated")
            if lifecycle == "expired":
                codes.append("thesis_watch_expired")
            if lifecycle != "confirmed" or (
                valid_until and now >= datetime.fromisoformat(valid_until)
            ):
                codes.append("thesis_watch_unconfirmed")
            if watch.state.get("evaluation_status") == "suspended_health":
                codes.append("thesis_watch_health_unavailable")
            observation_expiry = watch.state.get("observation", {}).get("valid_until")
            if observation_expiry and now >= datetime.fromisoformat(observation_expiry):
                codes.append("thesis_watch_evidence_expired")
            facts["watch"] = {"id": watch.id, "lifecycle": lifecycle, "valid_until": valid_until}
    facts["validation_codes"] = list(dict.fromkeys(codes))
    return facts["validation_codes"], facts


async def refresh_opportunity(
    session: AsyncSession, row: TradingOpportunityRow, *, now: datetime | None = None
) -> TradingOpportunityRow:
    now = now or utcnow()
    if row.status in TERMINAL:
        return row
    previous = row.status
    codes, facts = await evidence_state(session, row, now)
    if "thesis_expired" in codes or "thesis_watch_expired" in codes:
        transition(
            session,
            row,
            "expired",
            "thesis_horizon_elapsed" if "thesis_expired" in codes else "thesis_watch_expired",
            evidence=facts,
        )
    elif "thesis_watch_invalidated" in codes:
        transition(session, row, "invalidated", "thesis_watch_invalidated", evidence=facts)
    elif row.status == "confirmed" and codes:
        transition(session, row, "degraded", codes[0], evidence=facts)
    if row.status != previous:
        await wake_opportunity(session, row)
    return row


async def update_opportunity(
    session: AsyncSession, owner_id: str, agent_id: str, body: OpportunityUpdate
) -> TradingOpportunityRow:
    row = await owned_opportunity(session, owner_id, body.opportunity_id, lock=True)
    if row.agent_id != agent_id:
        raise LonoraError("opportunity_agent_mismatch", 403)
    if row.version != body.expected_version:
        raise LonoraError("version_conflict", 409)
    if row.status in TERMINAL:
        raise LonoraError("thesis_terminal", 409)
    if body.status in {"acted_on", "completed"}:
        raise LonoraError("thesis_execution_receipt_required", 409)
    definition = body.definition or ThesisDefinition.model_validate(row.payload["definition"])
    if definition.expires_at <= utcnow() and body.status != "expired":
        raise LonoraError("thesis_expired", 409)
    # Extending a confirmed horizon needs a new evidence set and an explicit new version.
    if (
        body.definition
        and body.definition.expires_at > row.expires_at
        and not body.supporting_decision_ids
    ):
        raise LonoraError("thesis_extension_evidence_required", 409)
    refs = body.supporting_decision_ids + body.contradicting_decision_ids
    await validate_references(session, owner_id, row.account_id, row.symbol, row.timeframe, refs)
    row.payload = {
        **row.payload,
        "definition": definition.model_dump(mode="json"),
        "supporting_decision_ids": list(dict.fromkeys(body.supporting_decision_ids)),
        "contradicting_decision_ids": list(dict.fromkeys(body.contradicting_decision_ids)),
    }
    row.expires_at = definition.expires_at
    codes, facts = await evidence_state(session, row, utcnow())
    if body.status == "confirmed" and codes:
        raise LonoraError(codes[0], 409)
    if body.status == "expired" and "thesis_expired" not in codes:
        raise LonoraError("thesis_expiry_rule_not_met", 409)
    if body.status == "invalidated" and not body.contradicting_decision_ids:
        raise LonoraError("thesis_invalidation_evidence_required", 409)
    row.last_validated_at = utcnow()
    transition(session, row, body.status, body.reason_code, evidence=facts)
    return row


async def require_entry_thesis(session: AsyncSession, owner_id: str, request: TradeRequest) -> None:
    if not request.thesis_id:
        return
    row = await owned_opportunity(session, owner_id, request.thesis_id, lock=True)
    if (row.account_id, row.symbol) != (request.account_id, request.symbol):
        raise LonoraError("thesis_execution_scope_mismatch", 409)
    if request.action not in ENTRY_ACTIONS:
        row.state = {**row.state, "pending_management_operation_id": request.operation_id}
        return  # Protective exits still use all normal execution/approval controls.
    codes, _ = await evidence_state(session, row, utcnow())
    if row.status != "confirmed" or codes:
        raise LonoraError(codes[0] if codes else "thesis_not_confirmed", 409)
    if row.state.get("entry_operation_id"):
        raise LonoraError("thesis_already_acted_on", 409)
    pending = row.state.get("pending_entry_operation_id")
    if pending and pending != request.operation_id:
        raise LonoraError("thesis_operation_unresolved", 409)
    direction = ThesisDefinition.model_validate(row.payload["definition"]).direction
    if not request.action.startswith(direction.lower()):
        raise LonoraError("thesis_execution_direction_mismatch", 409)
    row.state = {**row.state, "pending_entry_operation_id": request.operation_id}


async def sync_opportunity_execution(session: AsyncSession, journal: TradingJournalRow) -> None:
    if journal.execution_mode != "live":
        return
    identifier = journal.request.get("thesis_id")
    if not identifier or journal.status not in {"confirmed", "failed"}:
        return
    row = await owned_opportunity(session, journal.owner_id, str(identifier), lock=True)
    if journal.status == "failed":
        row.state = {
            **row.state,
            **{
                key: None
                for key in ("pending_entry_operation_id", "pending_management_operation_id")
                if row.state.get(key) == journal.operation_id
            },
        }
        return
    action = journal.request.get("action")
    state = {**row.state, "last_operation_id": journal.operation_id}
    if state.get("pending_management_operation_id") == journal.operation_id:
        state["pending_management_operation_id"] = None
    details = journal.result.get("details", {})
    row.state = state
    if action in ENTRY_ACTIONS and row.state.get("entry_operation_id") != journal.operation_id:
        row.state = {
            **state,
            "entry_operation_id": journal.operation_id,
            "pending_entry_operation_id": None,
            "entry_position_id": details.get("position_id")
            or (
                journal.result.get("broker_id")
                if details.get("simulation") and action in {"buy", "sell"}
                else None
            ),
        }
        transition(
            session,
            row,
            "acted_on",
            "thesis_entry_confirmed",
            evidence={
                "operation_id": journal.operation_id,
                "broker_id": journal.result.get("broker_id"),
            },
        )
    elif (
        action == "close_position"
        and journal.request.get("volume") is None
        and not details.get("partial_execution")
        and row.state.get("entry_position_id")
        and journal.request.get("position_id") == row.state.get("entry_position_id")
        and row.status != "completed"
    ):
        row.state = state
        transition(
            session,
            row,
            "completed",
            "thesis_position_closed",
            evidence={
                "operation_id": journal.operation_id,
                "broker_id": journal.result.get("broker_id"),
            },
        )


async def maintenance_opportunities(db: Database, owner_id: str) -> int:
    async with db.sessions() as session, session.begin():
        rows = list(
            await session.scalars(
                select(TradingOpportunityRow)
                .where(
                    TradingOpportunityRow.owner_id == owner_id,
                    or_(
                        TradingOpportunityRow.status.in_(
                            ["forming", "confirmed", "degraded", "acted_on"]
                        ),
                        TradingOpportunityRow.state["pending_entry_operation_id"]
                        .as_string()
                        .is_not(None),
                        TradingOpportunityRow.state["pending_management_operation_id"]
                        .as_string()
                        .is_not(None),
                    ),
                )
                .order_by(TradingOpportunityRow.updated_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            for key in ("pending_entry_operation_id", "pending_management_operation_id"):
                operation_id = row.state.get(key)
                if operation_id:
                    journal = await session.get(TradingJournalRow, operation_id)
                    if journal:
                        await sync_opportunity_execution(session, journal)
            await refresh_opportunity(session, row)
            row.updated_at = (
                utcnow()
            )  # Fair bounded polling; not a new evidence timestamp or event.
        return len(rows)


async def wake_opportunity(session: AsyncSession, row: TradingOpportunityRow) -> None:
    """Meaningful durable transition only; reuse work lane, receipts and same Agent."""
    agent = await session.get(AgentRow, row.agent_id)
    if agent is None or agent.paused or not row.thread_id:
        return
    key = "opportunity-wake:" + row.id + ":" + str(row.version)
    if await session.get(EffectReceiptRow, key):
        return
    work = await create_thread(
        session, row.owner_id, ThreadCreate(agent_id=agent.id), purpose="work"
    )
    identifier = stable_id(row.id, "wake:" + str(row.version))
    await create_run(
        session,
        row.owner_id,
        RunRequest(
            thread_id=work.id,
            agent_id=agent.id,
            trigger="watch",
            prompt="Inspect the saved opportunity transition and its actual evidence, explain the material change and whether re-analysis is needed. This read-only wake grants no trading authority.",
            metadata={
                "opportunity_id": row.id,
                "opportunity_version": row.version,
                "origin_thread_id": row.thread_id,
                "authority": "observe_only",
                "reason_code": row.state.get("reason_code"),
            },
        ),
        identifier,
    )
    session.add(
        EffectReceiptRow(
            key=key, result={"run_id": identifier, "opportunity_id": row.id, "version": row.version}
        )
    )
