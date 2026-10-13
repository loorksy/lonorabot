from typing import Any, cast

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
