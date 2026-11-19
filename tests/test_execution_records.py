"""Historical facts remain bounded, mode-specific and independent of today's market."""

from decimal import Decimal

from lonora_contracts.account import AccountState, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest
from lonora_db.schema import TradingJournalRow
from lonora_db.trading_journal import SERVER_EVIDENCE
from lonora_trading.journal import execution_evidence, record_excerpt


def test_execution_snapshot_keeps_target_and_labels_truncation():
    now = utcnow()
    snapshot = ExecutionSnapshot(
        account=AccountState(
            id="account",
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            currency="USD",
            margin=Decimal("0"),
            free_margin=Decimal("10000"),
            observed_at=now,
        ),
        positions=[
            Position(
                id=f"ticket-{i:03d}",
                symbol="EURUSDm",
                side="buy",
                volume=Decimal("0.1"),
                open_price=Decimal("1.1"),
                profit=Decimal("50"),
            )
            for i in range(150)
        ],
        orders=[],
        observed_at=now,
    )
    request = TradeRequest(
        account_id="account", symbol="EURUSDm", action="close_position", position_id="ticket-149"
    )
    evidence = execution_evidence(snapshot, request, phase="before_send")
    assert evidence["counts"] == {"positions": 150, "orders": 0}
    assert evidence["truncated"] and len(evidence["snapshot"]["positions"]) == 100
    assert evidence["snapshot"]["positions"][0]["id"] == "ticket-149"
    assert snapshot.positions[0].profit == 50
    assert evidence["target_source"] == "broker_adapter" and evidence["hidden_reasoning"] is None


def test_record_projection_does_not_mutate_or_expose_other_symbol_positions():
    row = TradingJournalRow(
        operation_id="operation",
        owner_id="owner",
        account_id="account",
        request={"symbol": "EURUSDm"},
        result={
            "details": {
                "adapter_private_field": "not a model evidence contract",
                "execution_evidence": {
                    "before_send": {
                        "snapshot": {
                            "positions": [
                                {"id": "a", "symbol": "EURUSDm"},
                                {"id": "b", "symbol": "BTCUSD.pro"},
                            ],
                            "orders": [],
                        }
                    }
                },
            }
        },
        updated_at=utcnow(),
    )
    data = record_excerpt(row, symbol="EURUSDm")
    assert data["historical_evidence_available"] and data["execution_authorized"] is False
    assert "adapter_private_field" not in data["result"]["details"]
    observed = data["result"]["details"]["execution_evidence"]["before_send"]
    assert [p["id"] for p in observed["snapshot"]["positions"]] == ["a"]
    assert (
        len(row.result["details"]["execution_evidence"]["before_send"]["snapshot"]["positions"])
        == 2
    )


def test_legacy_receipt_reports_missing_evidence_without_substitution():
    row = TradingJournalRow(
        operation_id="old-operation",
        owner_id="owner",
        account_id="account",
        request={"symbol": "EURUSDm"},
        result={"status": "confirmed", "details": {}},
        updated_at=utcnow(),
    )
    data = record_excerpt(row)
    assert data["historical_evidence_available"] is False
    assert data["result"]["details"] == {}


def test_older_risk_evidence_survives_receipts_and_reaches_the_record():
    assert {"risk_assessment", "admission_block"} <= set(SERVER_EVIDENCE)
    row = TradingJournalRow(
        operation_id="op-blocked",
        owner_id="owner",
        account_id="account",
        request={"symbol": "XAUUSD.r"},
        result={
            "operation_id": "op-blocked",
            "status": "failed",
            "code": "broker_reconciliation_required",
            "details": {
                "send_state": "not_sent",
                "admission_block": {"code": "broker_reconciliation_required"},
                "risk_assessment": {
                    "items": [{"symbol": "XAUUSD.r"}, {"symbol": "EURUSD.r"}],
                    "open_risk": "9",
                },
            },
        },
        updated_at=utcnow(),
    )
    details = record_excerpt(row, symbol="XAUUSD.r")["result"]["details"]
    assert details["admission_block"] == {"code": "broker_reconciliation_required"}
    assert details["risk_assessment"]["items"] == [{"symbol": "XAUUSD.r"}]
    assert details["risk_assessment"]["open_risk"] == "9"
