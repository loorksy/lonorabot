from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_market.instruments import resolve_instrument
from lonora_security.financial import validate_trade


async def preflight(broker: BrokerAdapter, request: TradeRequest) -> None:
    instrument = resolve_instrument(await broker.instruments(), request.symbol)
    validate_trade(request, instrument)
    await broker.account()
    if request.position_id:
        positions = await broker.positions()
        if not any(p.id == request.position_id and p.symbol == request.symbol for p in positions):
            raise LonoraError("position_not_found", 404)
    if request.order_id:
        orders = await broker.orders()
        if not any(o.id == request.order_id and o.symbol == request.symbol for o in orders):
            raise LonoraError("order_not_found", 404)
