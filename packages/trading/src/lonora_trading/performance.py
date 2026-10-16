"""Evidence-based quality summaries; price return is not monetary P/L or correctness."""

import json
from decimal import Decimal
from typing import Any

from lonora_contracts.shadow import PerformanceRead
from lonora_db.client import Database
from lonora_db.schema import ShadowTradeRow, TradingJournalRow
from sqlalchemy import select

MINIMUM_SAMPLE = 20


def quality_dimensions(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Bound projections regardless of the size of immutable decision evidence."""
    result: dict[str, Any] = {}
    for name in ("analysis", "entry", "management", "execution"):
        counts: dict[str, int] = {}
        examples: list[dict[str, Any]] = []
        for row in records:
            assessment = row.get("quality", {}).get(name, {})
            state = str(assessment.get("state") or "unavailable")[:80]
            counts[state] = counts.get(state, 0) + 1
            if len(examples) < 3:
                examples.append({"record_id": row["id"], "state": state})
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        result[name] = {
            "state_counts": dict(ordered[:16]),
            "other_state_count": sum(count for _, count in ordered[16:]),
            "examples": examples,
        }
    return result


def quality_summary(
    records: list[dict[str, Any]], *, mode: str, minimum_sample: int = MINIMUM_SAMPLE
) -> dict[str, Any]:
    threshold = max(MINIMUM_SAMPLE, minimum_sample)
    known = [
        Decimal(str(row["price_return_fraction"]))
        for row in records
        if row.get("price_return_fraction") is not None
    ]
    reasons: dict[str, int] = {}
    for row in records:
        for code in set(row.get("gate_codes", [])):
            reasons[code] = reasons.get(code, 0) + 1
    sample = len(records)
    return {
        "execution_mode": mode,
        "sample_count": sample,
        "minimum_sample": threshold,
        "sample_state": "sufficient_observations" if sample >= threshold else "insufficient_data",
        "known_price_return_count": len(known),
        "mean_observed_price_return_fraction": str(sum(known) / len(known)) if known else None,
        "positive_price_return_count": sum(value > 0 for value in known),
        "monetary_pnl": None,
        "monetary_pnl_code": "contract_currency_valuation_unavailable",
        "quality_dimensions": quality_dimensions(records),
        "repeated_gate_failures": [
            {"code": code, "count": count}
            for code, count in sorted(reasons.items())[:20]
            if count >= 3 and sample >= threshold
        ],
        "safety_policy_changed": False,
        "live_authority_granted": False,
        "interpretation_code": "price_return_not_account_profit_or_analysis_correctness",
    }


async def performance_snapshot(
    db: Database, owner_id: str, agent_id: str, params: PerformanceRead
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    async with db.sessions() as session:
        if params.execution_mode == "shadow":
            query = select(ShadowTradeRow).where(
                ShadowTradeRow.owner_id == owner_id,
                ShadowTradeRow.agent_id == agent_id,
                ShadowTradeRow.status == "closed",
            )
            if params.account_id:
                query = query.where(ShadowTradeRow.account_id == params.account_id)
            if params.symbol:
                query = query.where(ShadowTradeRow.symbol == params.symbol)
            rows = await session.scalars(
                query.order_by(ShadowTradeRow.updated_at.desc()).limit(1000)
            )
            for row in rows:
                if (
                    params.strategy_version
                    and row.payload.get("strategy_version") != params.strategy_version
                ):
                    continue
                records.append(
                    {
                        "id": row.id,
                        "symbol": row.symbol,
                        "timeframe": row.payload.get("timeframe"),
                        "strategy_version": row.payload.get("strategy_version"),
                        "setup_key": row.payload.get("setup_key"),
                        "regime": row.payload.get("regime"),
                        "status": row.status,
                        "price_return_fraction": row.state.get("price_return_fraction"),
                        "quality": row.state.get("quality", {}),
                        "gate_codes": row.state.get("gate_codes", []),
                    }
                )
        else:
            query = select(TradingJournalRow).where(
                TradingJournalRow.owner_id == owner_id,
                TradingJournalRow.execution_mode == "live",
                TradingJournalRow.status.in_(["confirmed", "failed"]),
            )
            if params.account_id:
                query = query.where(TradingJournalRow.account_id == params.account_id)
            rows = await session.scalars(
                query.order_by(TradingJournalRow.updated_at.desc()).limit(1000)
            )
            from lonora_db.schema import RunRow

            for entry in rows:
                # Historical entries without a frozen strategy identity cannot
                # satisfy a strategy filter by borrowing today's Agent/thesis.
                if params.strategy_version:
                    continue
                details = entry.result.get("details", {})
                origin = details.get("execution", {})
                attributed_agent = origin.get("agent_id")
                if not attributed_agent:
                    # Legacy receipts may only have a fenced Run reference.
                    lease = details.get("lease")
                    run = await session.get(RunRow, lease["run_id"]) if lease else None
                    attributed_agent = run.agent_id if run else None
                if attributed_agent != agent_id or (
                    params.symbol and entry.request.get("symbol") != params.symbol
                ):
                    continue
                quality = entry.result.get("details", {}).get("execution_quality", {})
                records.append(
                    {
                        "id": entry.operation_id,
                        "symbol": entry.request.get("symbol"),
                        "quality": {"execution": quality},
                        "gate_codes": [entry.result["code"]]
                        if entry.status == "failed" and entry.result.get("code")
                        else [],
                    }
                )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        identity = json.dumps(
            [
                record.get(key)
                for key in ("symbol", "timeframe", "strategy_version", "setup_key", "regime")
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        grouped.setdefault(identity, []).append(record)
    return {
        **quality_summary(
            records, mode=params.execution_mode, minimum_sample=params.minimum_sample
        ),
        "groups": [
            {
                "dimension_key": key,
                **quality_summary(
                    group, mode=params.execution_mode, minimum_sample=params.minimum_sample
                ),
            }
            for key, group in sorted(grouped.items())[:30]
        ],
        "records_scanned": len(records),
        "scan_limit": 1000,
    }
