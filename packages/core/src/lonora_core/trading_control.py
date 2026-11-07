from lonora_contracts.trading import TradingControl

from .user_error import LonoraError


def require_trading(control: TradingControl, *, risk_reducing: bool = False) -> None:
    """Trading OFF and Emergency Stop stop new risk; they never trap an exit.

    ``risk_reducing`` must come from the financial boundary's own classification of
    the current broker target (lonora_trading.admission.risk_reducing), never from a
    caller's or model's description of the request.
    """
    if risk_reducing:
        return
    if control.emergency_stop:
        raise LonoraError("emergency_stop", 409)
    if not control.enabled:
        raise LonoraError("trading_disabled", 409)
