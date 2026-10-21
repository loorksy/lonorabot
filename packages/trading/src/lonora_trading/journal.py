from copy import deepcopy
from typing import Any, cast

from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionSnapshot
from lonora_contracts.shadow import ExecutionMode
from lonora_contracts.trading import TradeRequest
from lonora_contracts.trading_goal import GoalExecution
from lonora_db.schema import TradingJournalRow


def journal_data(row: TradingJournalRow) -> dict[str, Any]:
    execution = row.result.get("details", {}).get("execution", {})
    if not isinstance(execution, dict):
        execution = {}
    origin = cast(dict[str, Any], execution)
    return {
        "run_id": origin.get("run_id"),
        "agent_id": origin.get("agent_id"),
        "provider": origin.get("provider"),
        "broker_account_id": origin.get("broker_account_id"),
        "operation_id": row.operation_id,
        "account_id": row.account_id,
        "status": row.status,
        "request": row.request,
        "result": row.result,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "updated_at": row.updated_at.isoformat(),
    }


def execution_evidence(
    snapshot: ExecutionSnapshot,
    request: TradeRequest,
    *,
    mode: ExecutionMode,
    phase: str,
    goal: GoalExecution | None = None,
    policy: ExecutionPolicy | None = None,
) -> dict[str, Any]:
    """Persist only typed facts read at this boundary, never model reasoning or secrets."""
    data = snapshot.model_dump(mode="json")
    counts = {name: len(data[name]) for name in ("positions", "orders")}
    for name, target in (("positions", request.position_id), ("orders", request.order_id)):
        # Retain the actual management target even on very large accounts.
        values = sorted(data[name], key=lambda item: (item["id"] != target, item["id"]))
        data[name] = values[:100]
        if mode == "shadow" and name == "positions":
            data[name] = [{**item, "profit": None} for item in data[name]]
    return {
        "schema_version": 1,
        "logic_version": "execution-boundary-v1",
        "phase": phase,
        "execution_mode": mode,
        "snapshot": data,
        "counts": counts,
        "truncated": any(count > 100 for count in counts.values()),
        "account_source": "broker_adapter",
        "target_source": "virtual_book" if mode == "shadow" else "broker_adapter",
        "policy": policy.model_dump(mode="json") if policy else None,
        "goal": goal.model_dump(mode="json") if goal else None,
        "thesis_id": request.thesis_id,
        "hidden_reasoning": None,
    }


def record_excerpt(row: TradingJournalRow, *, symbol: str | None = None) -> dict[str, Any]:
    """Historical model view, bounded and scoped without changing the journal."""
    result = deepcopy(row.result)
    details = result.get("details", {})
    # SDK payloads are not an evidence format and do not belong in model context.
    result["details"] = {
        key: details[key]
        for key in (
            "execution",
            "execution_evidence",
            "execution_quality",
            "verification",
            "price",
            "volume",
            "mode",
            "virtual_id",
            "virtual_status",
            "fill_model",
            "monetary_pnl",
        )
        if key in details
    }
    if symbol:
        for observed in result["details"].get("execution_evidence", {}).values():
            snapshot = observed.get("snapshot")
            if isinstance(snapshot, dict):
                for key in ("positions", "orders"):
                    snapshot[key] = [
                        item
                        for item in cast(list[dict[str, Any]], snapshot[key])
                        if item["symbol"] == symbol
                    ]
                observed["projection_scope"] = {"symbol": symbol}
    return {
        "operation_id": row.operation_id,
        "account_id": row.account_id,
        "execution_mode": row.execution_mode,
        "request": row.request,
        "result": result,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "recorded_at": row.updated_at.isoformat(),
        "historical_evidence_available": bool(details.get("execution_evidence")),
        "execution_authorized": False,
    }
