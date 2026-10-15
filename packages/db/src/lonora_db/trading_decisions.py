"""Immutable decision snapshots in the existing durable event ledger.

These are historical decisions, not a second financial execution journal.
Public event cursor bookkeeping is excluded from the typed decision payload.
"""

from typing import Any

from lonora_contracts.trading_decision import TradingDecision
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import EffectReceiptRow, EventRow

DECISION_KIND = "trading.decision_recorded"


async def store_decision(
    session: AsyncSession, decision: TradingDecision, *, thread_id: str, intent: str
) -> TradingDecision:
    receipt = await session.get(EffectReceiptRow, "decision:" + decision.id)
    if receipt:
        if receipt.result.get("intent") != intent:
            raise LonoraError("decision_intent_conflict", 409)
        return TradingDecision.model_validate(receipt.result["decision"])
    data = decision.model_dump(mode="json")
    emit(
        session,
        decision.owner_id,
        DECISION_KIND,
        thread_id=thread_id,
        agent_id=decision.agent_id,
        run_id=decision.run_id,
        payload={"decision": data},
    )
    session.add(
        EffectReceiptRow(key="decision:" + decision.id, result={"intent": intent, "decision": data})
    )
    return decision


async def read_decision(session: AsyncSession, owner_id: str, decision_id: str) -> TradingDecision:
    row = await session.scalar(
        select(EventRow).where(
            EventRow.owner_id == owner_id,
            EventRow.kind == DECISION_KIND,
            EventRow.payload["decision"]["id"].as_string() == decision_id,
        )
    )
    if row is None:
        raise LonoraError("decision_not_found", 404)
    return TradingDecision.model_validate(row.payload["decision"])


async def decision_history(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None = None,
    account_id: str | None = None,
    symbol: str | None = None,
    limit: int = 5,
) -> list[TradingDecision]:
    query = select(EventRow).where(EventRow.owner_id == owner_id, EventRow.kind == DECISION_KIND)
    if agent_id:
        query = query.where(EventRow.agent_id == agent_id)
    for key, value in (("account_id", account_id), ("symbol", symbol)):
        if value:
            query = query.where(EventRow.payload["decision"][key].as_string() == value)
    rows = await session.scalars(
        query.order_by(EventRow.cursor.desc()).limit(max(1, min(limit, 20)))
    )
    return [TradingDecision.model_validate(row.payload["decision"]) for row in rows]


def decision_changes(earlier: TradingDecision, later: TradingDecision) -> dict[str, Any]:
    if (earlier.owner_id, earlier.account_id, earlier.symbol, earlier.timeframe) != (
        later.owner_id,
        later.account_id,
        later.symbol,
        later.timeframe,
    ):
        raise LonoraError("decision_comparison_scope_mismatch", 409)
    if earlier.recorded_at > later.recorded_at:
        raise LonoraError("decision_comparison_order_invalid", 422)

    def material(record: TradingDecision) -> dict[str, Any]:
        e = record.evidence
        return {
            "action": record.action,
            "gate_codes": record.gate_codes,
            "bid": str(e.quote.bid) if e.quote else None,
            "ask": str(e.quote.ask) if e.quote else None,
            "spread": str(e.quote.ask - e.quote.bid) if e.quote else None,
            "health": [(h.resource, h.state, h.reason_code) for h in e.health],
            "positions": [
                p.model_dump(mode="json", exclude={"profit"})
                for p in sorted(e.positions, key=lambda p: p.id)[:20]
            ],
            "position_count": len(e.positions),
            "orders": [
                o.model_dump(mode="json") for o in sorted(e.orders, key=lambda o: o.id)[:20]
            ],
            "order_count": len(e.orders),
        }

    before, after = material(earlier), material(later)
    return {
        "earlier_id": earlier.id,
        "later_id": later.id,
        "changes": {
            key: {"before": value, "after": after[key]}
            for key, value in before.items()
            if value != after[key]
        },
    }


def decision_summary(decision: TradingDecision) -> dict[str, Any]:
    return {
        key: getattr(decision, key)
        for key in (
            "id",
            "agent_id",
            "account_id",
            "symbol",
            "timeframe",
            "action",
            "requested_action",
            "summary",
            "gate_codes",
        )
    } | {
        "recorded_at": decision.recorded_at.isoformat(),
        "evidence_id": decision.evidence.id,
        "execution_authorized": False,
    }


def decision_excerpt(decision: TradingDecision) -> dict[str, Any]:
    """Bound model context; the immutable record and owner API retain full evidence."""
    result = decision.model_dump(mode="json")
    evidence = result["evidence"]
    result["evidence_counts"] = {
        key: len(evidence[key]) for key in ("candles", "positions", "orders")
    }
    evidence["positions"] = evidence["positions"][:20]
    evidence["orders"] = evidence["orders"][:20]
    return result
