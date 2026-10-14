"""A bound bot uses its pair and does not treat letter case as a different market."""

from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import BINDING_POLICY, assert_market_binding, binding_context
from lonora_db.schema import AgentRow
from lonora_tools.market_binding import align_payload, fill_bound_fields
from pydantic import BaseModel


class Quote(BaseModel):
    account_id: str
    symbol: str
    volume: str | None = None


def main() -> None:
    agent = AgentRow(
        owner_id="owner",
        name="Bound",
        trading_account_id="Acc-1",
        trading_symbol="XAUUSDm",
    )
    aligned = align_payload(
        agent,
        {"account_id": "acc-1", "symbol": "xauusdm", "nested": {"symbol": "XAUUSDM"}},
    )
    assert aligned == {
        "account_id": "Acc-1",
        "symbol": "XAUUSDm",
        "nested": {"symbol": "XAUUSDm"},
    }
    filled = fill_bound_fields(agent, {"volume": "1"}, set(Quote.model_fields))
    assert filled["account_id"] == "Acc-1" and filled["symbol"] == "XAUUSDm"
    assert_market_binding(agent, "ACC-1", "XAUUSDM")
    for account_id, symbol, code in (
        ("other", "XAUUSDm", "agent_trading_account_mismatch"),
        ("Acc-1", "EURUSDm", "agent_trading_symbol_mismatch"),
    ):
        try:
            assert_market_binding(agent, account_id, symbol)
        except LonoraError as error:
            assert error.code == code, error.code
        else:
            raise AssertionError(code)
    text = binding_context(agent)
    assert "XAUUSDm" in text and "immutable_trading_market" in text
    assert "Never ask which pair" in text and "Speech and chat text are not approval" in text
    assert BINDING_POLICY in text
    unbound = AgentRow(owner_id="owner", name="Legacy")
    assert binding_context(unbound) == ""
    assert_market_binding(unbound, "anything", "EURUSDm")
    print("PASS bound pair is filled; letter case is the same market; another pair is refused")


if __name__ == "__main__":
    main()
