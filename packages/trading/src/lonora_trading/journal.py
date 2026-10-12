from typing import Any

from lonora_db.schema import TradingJournalRow


def journal_data(row: TradingJournalRow) -> dict[str, Any]:
    return {
        "operation_id": row.operation_id,
        "account_id": row.account_id,
        "status": row.status,
        "request": row.request,
        "result": row.result,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "updated_at": row.updated_at.isoformat(),
    }
