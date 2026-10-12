from decimal import Decimal

from lonora_contracts.market import Instrument
from lonora_contracts.trading import TradeRequest
from lonora_core.trading_run_market import require_exact_symbol
from lonora_core.user_error import LonoraError


def validate_trade(request: TradeRequest, instrument: Instrument) -> None:
    require_exact_symbol(request.symbol, instrument.symbol)
    if request.volume is not None:
        volume = request.volume
        if not instrument.volume_min <= volume <= instrument.volume_max:
            raise LonoraError("volume_out_of_range")
        if (volume - instrument.volume_min) % instrument.volume_step != Decimal(0):
            raise LonoraError("volume_step_mismatch")
    for value in (request.price, request.stop_loss, request.take_profit):
        if value is not None and value % instrument.tick_size != Decimal(0):
            raise LonoraError("price_tick_mismatch")
