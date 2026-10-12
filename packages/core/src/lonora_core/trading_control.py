from lonora_contracts.trading import TradingControl

from .user_error import LonoraError


def require_trading(control: TradingControl) -> None:
    if control.emergency_stop:
        raise LonoraError("emergency_stop", 409)
    if not control.enabled:
        raise LonoraError("trading_disabled", 409)
