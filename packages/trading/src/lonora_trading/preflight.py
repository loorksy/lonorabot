from decimal import Decimal

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest
from lonora_core.trading_run_market import require_exact_symbol
from lonora_core.user_error import LonoraError
from lonora_security.financial import validate_trade


async def preflight(broker: BrokerAdapter, request: TradeRequest) -> ExecutionSnapshot:
    instrument = None
    if request.action != "cancel_order":
        instrument = await broker.instrument(request.symbol)
        validate_trade(request, instrument)
    account = await broker.account()
    account.id = request.account_id
    if account.trade_allowed is False or account.investor_mode is True:
        raise LonoraError("broker_trading_not_allowed", 409)
    positions = await broker.positions()
    orders = await broker.orders()
    quote = None
    target_order = None
    position = None
    if request.position_id:
        position = next(
            (p for p in positions if p.id == request.position_id and p.symbol == request.symbol),
            None,
        )
        if position is None:
            raise LonoraError("position_not_found", 404)
        if (
            request.action == "close_position"
            and request.volume is not None
            and request.volume > position.volume
        ):
            raise LonoraError("position_volume_exceeded", 409)
        if request.action == "close_position" and request.volume is not None:
            assert instrument is not None
            remaining = position.volume - request.volume
            if remaining and (
                remaining < instrument.volume_min
                or (remaining - instrument.volume_min) % instrument.volume_step != 0
            ):
                raise LonoraError("position_remaining_volume_invalid", 409)

    if request.order_id:
        target_order = next(
            (o for o in orders if o.id == request.order_id and o.symbol == request.symbol), None
        )
        if target_order is None:
            raise LonoraError("order_not_found", 404)
    pending = {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}
    if request.action in pending | {"buy", "sell"} or request.action in {
        "modify_order",
        "modify_position",
    }:
        kind = (
            request.action
            if request.action in pending | {"buy", "sell"}
            else str(position.side if position else target_order.side if target_order else "")
            .removeprefix("ORDER_TYPE_")
            .casefold()
        )
        if kind not in pending | {"buy", "sell"}:
            raise LonoraError("unsupported_pending_order", 409)
        price = (
            request.price
            if request.price is not None
            else target_order.price
            if target_order
            else None
        )
        quote = await broker.quote(request.symbol)
        require_exact_symbol(request.symbol, quote.symbol)
        if (
            quote.observed_at.tzinfo is None
            or not -5 <= (utcnow() - quote.observed_at).total_seconds() <= 60
        ):
            raise LonoraError("market_quote_stale", 409)
        market = quote.ask if kind.startswith("buy") else quote.bid
        if kind in {"buy", "sell"}:
            price = market
        else:
            assert price is not None
            below = kind in {"buy_limit", "sell_stop"}
            wrong_side = price >= market if below else price <= market
            if wrong_side:
                raise LonoraError("pending_price_wrong_side", 409)
        assert price is not None
        stop_loss = (
            None
            if request.clear_stop_loss
            else request.stop_loss
            if request.stop_loss is not None
            else target_order.stop_loss
            if target_order
            else position.stop_loss
            if position
            else None
        )
        take_profit = (
            None
            if request.clear_take_profit
            else request.take_profit
            if request.take_profit is not None
            else target_order.take_profit
            if target_order
            else position.take_profit
            if position
            else None
        )
        buy = kind.startswith("buy")
        reference = (quote.bid if buy else quote.ask) if kind in {"buy", "sell"} else price
        if stop_loss and (stop_loss >= reference if buy else stop_loss <= reference):
            raise LonoraError("stop_loss_wrong_side", 409)
        if take_profit and (take_profit <= reference if buy else take_profit >= reference):
            raise LonoraError("take_profit_wrong_side", 409)
        assert instrument is not None
        minimum = instrument.stops_level * (
            instrument.point_size or Decimal(10) ** -instrument.digits
        )
        if kind in pending and minimum and abs(price - market) < minimum:
            raise LonoraError("pending_stops_level", 409)
        if stop_loss is not None and abs(reference - stop_loss) < minimum:
            raise LonoraError("stop_loss_stops_level", 409)
        if take_profit is not None and abs(reference - take_profit) < minimum:
            raise LonoraError("take_profit_stops_level", 409)

    if quote is None and request.action == "close_position":
        quote = await broker.quote(request.symbol)
        require_exact_symbol(request.symbol, quote.symbol)
    return ExecutionSnapshot(
        account=account, positions=positions, orders=orders, quote=quote, observed_at=utcnow()
    )
