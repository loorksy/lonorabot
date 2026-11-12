"""Realized P&L of broker deals.

A deal's contribution counts conservatively (``deal_pnl``): trade deals
(``DEAL_TYPE_BUY``/``DEAL_TYPE_SELL``) with their profit, commission and swap; balance,
credit and bonus cash flows not at all; and every other deal type (correction, charge,
commission, interest, dividend, tax, a cancelled deal, an unknown or missing type) only
when its total is negative, so a non-trading credit never offsets a trading loss.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from lonora_core.user_error import LonoraError

# Deal types by their ``DEAL_TYPE_`` suffix (MetaTrader/MetaApi names).
TRADE_DEALS = frozenset({"BUY", "SELL"})
CASH_FLOW_DEALS = frozenset({"BALANCE", "CREDIT", "BONUS"})


def deal_pnl(deal: dict[str, Any]) -> Decimal:
    """A deal's contribution to today's P&L; only trade deals may add a gain."""
    kind = str(deal.get("type") or "").strip().upper().removeprefix("DEAL_TYPE_")
    if kind in CASH_FLOW_DEALS:
        return Decimal(0)  # Deposits, withdrawals and broker credit are not trading P&L.
    total = Decimal(0)
    for key in ("profit", "commission", "swap"):
        raw = deal.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as error:
            raise LonoraError("risk_daily_history_invalid", 409) from error
        if not value.is_finite():
            raise LonoraError("risk_daily_history_invalid", 409)
        total += value
    # A non-trading adjustment counts against the limit, never for it.
    return total if kind in TRADE_DEALS else min(total, Decimal(0))
