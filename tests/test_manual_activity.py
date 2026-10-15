"""External activity provenance uses journal identity and broker facts, not names."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from lonora_contracts.account import Order, Position
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_db.schema import TradingJournalRow
from lonora_trading.manual_activity import detect_activity

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def position() -> Position:
    return Position(
        id="owner-ticket",
        symbol="XAUUSDm",
        side="buy",
        volume=Decimal("0.2"),
        open_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
    )


def prior(
    positions: list[Position] | None = None, orders: list[Order] | None = None
) -> BrokerRecoverySnapshot:
    return BrokerRecoverySnapshot(
        status="connected",
        reason_code="broker_reconciled",
        since=NOW,
        observed_at=NOW,
        positions=positions or [],
        orders=orders or [],
    )


def test_same_state_profit_and_decimal_scale_are_not_interventions() -> None:
    original = position()
    changed = original.model_copy(
        update={
            "profit": Decimal(123),
            "volume": Decimal("0.20"),
            "stop_loss": Decimal("95.00"),
            "operation_id": "later-attribution",
        }
    )
    assert (
        detect_activity(
            "account",
            prior([original]),
            [changed],
            [],
            [],
            revision=2,
            now=NOW + timedelta(seconds=10),
        )
        == []
    )


def test_external_position_open_modify_partial_close_full_close() -> None:
    original = position()
    opened = detect_activity("account", prior(), [original], [], [], revision=2, now=NOW)
    assert (
        opened[0].change == "opened"
        and opened[0].origin == "external"
        and opened[0].owner_rationale is None
    )
    changed = original.model_copy(update={"stop_loss": Decimal(97), "take_profit": Decimal(115)})
    modified = detect_activity("account", prior([original]), [changed], [], [], revision=3, now=NOW)
    assert modified[0].change == "modified" and modified[0].current == changed
    partial = changed.model_copy(update={"volume": Decimal("0.1")})
    assert (
        detect_activity("account", prior([changed]), [partial], [], [], revision=4, now=NOW)[
            0
        ].change
        == "partial_close"
    )
    closed = detect_activity("account", prior([partial]), [], [], [], revision=5, now=NOW)
    assert closed[0].change == "closed" and closed[0].current is None
    assert len({opened[0].id, modified[0].id, closed[0].id}) == 3


def test_pending_order_lifecycle_and_exact_suffix() -> None:
    order = Order(
        id="broker-order",
        symbol="US500.cash",
        side="buy_limit",
        volume=Decimal("0.2"),
        price=Decimal(99),
    )
    opened = detect_activity("account", prior(), [], [order], [], revision=1, now=NOW)
    assert opened[0].resource == "order" and opened[0].symbol == "US500.cash"
    changed = order.model_copy(update={"price": Decimal(98), "stop_loss": Decimal(95)})
    assert (
        detect_activity("account", prior(orders=[order]), [], [changed], [], revision=2, now=NOW)[
            0
        ].change
        == "modified"
    )
    assert (
        detect_activity("account", prior(orders=[changed]), [], [], [], revision=3, now=NOW)[
            0
        ].change
        == "cancelled"
    )


def test_journal_origin_requires_exact_identity_not_comment_or_ticket_shape() -> None:
    original = position().model_copy(update={"operation_id": "operation-actual"})
    entry = TradingJournalRow(
        operation_id="operation-actual",
        owner_id="owner",
        account_id="account",
        request_hash="fixture",
        request={"symbol": original.symbol, "action": "buy"},
        status="confirmed",
        result={"broker_id": original.id},
        updated_at=NOW,
    )
    observed = detect_activity("account", prior(), [original], [], [entry], revision=1, now=NOW)
    assert observed[0].origin == "lonora"
    unrelated = original.model_copy(update={"id": "different-ticket", "operation_id": None})
    assert (
        detect_activity("account", prior(), [unrelated], [], [entry], revision=2, now=NOW)[0].origin
        == "external"
    )
