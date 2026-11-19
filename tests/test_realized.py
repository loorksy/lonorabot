"""Realized P&L of broker deals (``lonora_trading.realized``)."""

import pytest
from lonora_core.user_error import LonoraError
from lonora_trading.realized import deal_pnl


def test_non_trading_credits_never_count_as_a_gain() -> None:
    # Trade deals count in full, gains included.
    assert deal_pnl({"type": "DEAL_TYPE_BUY", "profit": "40", "commission": "-2"}) == 38
    assert deal_pnl({"type": "DEAL_TYPE_SELL", "profit": "-10", "swap": "-1"}) == -11
    # Cash flows are not P&L in either direction.
    for kind in ("DEAL_TYPE_BALANCE", "DEAL_TYPE_CREDIT", "DEAL_TYPE_BONUS"):
        assert deal_pnl({"type": kind, "profit": "500"}) == 0
        assert deal_pnl({"type": kind, "profit": "-500"}) == 0
    # Every other adjustment counts only as a loss.
    for kind in (
        "DEAL_TYPE_CORRECTION",
        "DEAL_TYPE_INTEREST",
        "DEAL_DIVIDEND",
        "DEAL_DIVIDEND_FRANKED",
        "DEAL_TYPE_CHARGE",
        "DEAL_TAX",
        "DEAL_TYPE_COMMISSION_DAILY",
        "DEAL_TYPE_BUY_CANCELED",
        "",
    ):
        assert deal_pnl({"type": kind, "profit": "100"}) == 0, kind
        assert deal_pnl({"type": kind, "profit": "-7"}) == -7, kind
    assert deal_pnl({"profit": "25"}) == 0  # Missing type: never a gain.


def test_unreadable_values_are_refused() -> None:
    assert deal_pnl({"type": "DEAL_TYPE_CREDIT", "profit": "-1"}) == 0
    with pytest.raises(LonoraError, match="risk_daily_history_invalid"):
        deal_pnl({"profit": "not-a-number"})
