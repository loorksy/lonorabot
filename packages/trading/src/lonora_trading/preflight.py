from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_security.financial import validate_trade


async def preflight(broker: BrokerAdapter, request: TradeRequest) -> None:
    instrument = await broker.instrument(request.symbol)
    validate_trade(request, instrument)
    await broker.account()
    if request.position_id:
        positions = await broker.positions()
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
    if request.order_id:
        orders = await broker.orders()
        if not any(o.id == request.order_id and o.symbol == request.symbol for o in orders):
            raise LonoraError("order_not_found", 404)
