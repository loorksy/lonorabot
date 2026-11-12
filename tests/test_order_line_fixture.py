"""The order rows the web order line is tested with are the executor's real output.

``tests/fixtures/order-rows.json`` holds the journal API rows (``journal_data``) of a request the
boundary stopped before the broker (``not_sent``) and of a broker rejection (the MetaApi adapter's
``failed`` result). The web tests (tests/web/agent-status.test.ts, openui-chat-ux.spec.mjs) draw
the order line and its sheet from this file, so a change in the executor's shape breaks here.
Regenerate with ``LONORA_WRITE_FIXTURES=1``.
"""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.schema import TradingJournalRow
from lonora_trading.execution import not_sent
from lonora_trading.journal import journal_data

FIXTURE = Path(__file__).parent / "fixtures" / "order-rows.json"
AT = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)


def row(request: TradeRequest, result: TradeResult) -> dict[str, Any]:
    journal = TradingJournalRow(
        operation_id=request.operation_id,
        owner_id="owner",
        account_id=request.account_id,
        request_hash="hash",
        request=request.model_dump(mode="json", exclude_none=True),
        status=result.status,
        result=result.model_dump(mode="json"),
        submitted_at=AT,
        updated_at=AT,
    )
    return journal_data(journal)


def rows() -> dict[str, Any]:
    blocked = TradeRequest(
        operation_id="op-not-sent",
        account_id="acct",
        action="buy",
        symbol="XAUUSD",
        volume=Decimal("0.1"),
    )
    rejected = TradeRequest(
        operation_id="op-rejected",
        account_id="acct",
        action="sell",
        symbol="XAUUSD",
        volume=Decimal("0.2"),
    )
    return {
        # The boundary stopped it (an unresolved operation on this market): never sent to the
        # broker.
        "not_sent": row(blocked, not_sent(blocked, "broker_reconciliation_required")),
        # The broker refused it: metaapi.py's failed result with the broker's own description.
        "rejected": row(
            rejected,
            TradeResult(
                operation_id=rejected.operation_id,
                status="failed",
                code="TRADE_RETCODE_NO_MONEY",
                details={
                    "numeric_code": 10019,
                    "description": "Not enough money to complete the request",
                    "send_state": "sent",
                },
            ),
        ),
    }


def test_the_web_order_rows_are_the_executors_own_output() -> None:
    current = json.loads(json.dumps(rows(), sort_keys=True, default=str))
    if os.environ.get("LONORA_WRITE_FIXTURES"):
        FIXTURE.write_text(json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    assert json.loads(FIXTURE.read_text()) == current
    assert current["not_sent"]["send_state"] == "not_sent"
    assert current["not_sent"]["status"] == "failed"
