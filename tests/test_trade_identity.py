"""A stored trade request keeps its identity when the code around it moves (14.3.9).

For every unresolved journal row, ``trade_fingerprint`` and the operation-id derivation
must give the same value before and after a change. The expected values below were
computed on the code before ``AuthorityAction`` moved to ``lonora_contracts.trading`` and
typed ``TradeRequest.action`` (W-AUTH A2); a test that fails here changes the identity of
every stored request.
"""

from typing import Any

from lonora_contracts.trading import AnnotatedTradeRequest, TradeRequest
from lonora_trading.idempotency import operation_id, trade_fingerprint

# Each request as a journal row and a Trade Approval row store it (``model_dump(mode="json")``).
ENTRY: dict[str, Any] = {
    "account_id": "golden-account",
    "action": "buy_limit",
    "clear_stop_loss": False,
    "clear_take_profit": False,
    "operation_id": "golden-operation",
    "order_id": None,
    "position_id": None,
    "price": "2350.5",
    "stop_loss": "2340",
    "symbol": "XAUUSD",
    "take_profit": "2375.75",
    "thesis_id": None,
    "volume": "0.25",
}
MODIFY: dict[str, Any] = {
    "account_id": "golden-account",
    "action": "modify_position",
    "clear_stop_loss": True,
    "clear_take_profit": False,
    "operation_id": "golden-modify",
    "order_id": None,
    "position_id": "P-42",
    "price": None,
    "stop_loss": None,
    "symbol": "EURUSD",
    "take_profit": "1.1",
    "thesis_id": "golden-thesis",
    "volume": None,
}


def execute_arguments(stored: dict[str, Any]) -> dict[str, Any]:
    """The arguments trade_execute derives the operation id from: the validated tool input
    without the operation id, the annotation, the key and the defaults it drops
    (``lonora_tools.trade.execute``)."""
    args = AnnotatedTradeRequest.model_validate(
        {**stored, "reason": "golden", "label": "golden"}
    ).model_dump(mode="json")
    for name in ("operation_id", "reason", "tolerance", "label", "key"):
        args.pop(name)
    if args.get("thesis_id") is None:
        args.pop("thesis_id")
    for name in ("clear_stop_loss", "clear_take_profit"):
        if args[name] is False:
            args.pop(name)
    return args


def test_a_stored_request_keeps_its_fingerprint_and_its_dump() -> None:
    for stored, fingerprint in (
        (ENTRY, "ebcddfa5085b3eb3acab7d003aa53190bfa4e53ec0f631d54890132f14292edc"),
        (MODIFY, "c844796f395ec6545a329136c5fe826497b8960c654ec05c020cec899478c24d"),
    ):
        request = TradeRequest.model_validate(stored)
        assert request.model_dump(mode="json") == stored
        assert trade_fingerprint(request) == fingerprint


def test_a_request_keeps_its_operation_id() -> None:
    for stored, derived in (
        (ENTRY, "8c24b71a-0fbf-5084-b12b-27b7bffc6be0"),
        (MODIFY, "4ff3cc56-52c9-5880-85cd-262a20b816ed"),
    ):
        args = execute_arguments(stored)
        assert operation_id("golden-run", "golden-agent", args, None) == derived
    # With the CLI's --key the operation id is the agent's and the key's alone (7.3.5).
    keyed = operation_id("golden-run", "golden-agent", execute_arguments(ENTRY), "golden-key")
    assert keyed == "963c7c1b-2493-575f-be51-8f0900a9d3d4"
