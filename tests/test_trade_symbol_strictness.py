"""A new order names the account's exact symbol; an exit is never held back by the catalogue."""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from lonora_contracts.account import Position
from lonora_contracts.trading import TradeRequest
from lonora_tools import trade
from lonora_tools.symbols import SymbolNotResolved

LISTED = ["EURUSDm", "XAUUSDm"]


def position(identifier: str, symbol: str) -> Position:
    return Position(
        id=identifier,
        symbol=symbol,
        side="buy",
        volume=Decimal("0.01"),
        open_price=Decimal(4100),
        profit=Decimal(0),
    )


class Context:
    owner_id, agent_id, call_id = "owner", "agent", "call"
    lease = SimpleNamespace(run_id="run")

    def __init__(self, positions: list[Position], symbols: Any = None):
        @asynccontextmanager
        async def sessions():
            yield SimpleNamespace(get=AsyncMock(return_value=None))

        self.db = SimpleNamespace(sessions=sessions)
        broker = SimpleNamespace(
            symbols=symbols or AsyncMock(return_value=list(LISTED)),
            positions=AsyncMock(return_value=positions),
        )
        self.brokers = SimpleNamespace(get=AsyncMock(return_value=broker))


async def sent(tool: Any, context: Context, args: dict[str, Any]) -> list[TradeRequest]:
    """The requests a tool call would put on an approval card or send under a grant."""
    captured: list[TradeRequest] = []

    async def approved(_: Any, requests: list[TradeRequest]) -> dict[str, Any]:
        captured.extend(requests)
        return {}

    with (
        patch.object(trade, "agent_binding", AsyncMock()),
        patch.object(trade, "require_lease", AsyncMock()),
        patch.object(trade, "approved_execution", approved),
    ):
        await tool(context, {"account_id": "account", **args})
    return captured


@pytest.mark.asyncio
@pytest.mark.parametrize("named", ["XAUUSD", "gold", "الذهب", "XAUUSDT", "XAU"])
async def test_a_new_order_never_reaches_a_symbol_the_request_did_not_name(named: str) -> None:
    order = {"action": "buy", "volume": "0.01", "symbol": named}
    with pytest.raises(SymbolNotResolved):
        await sent(trade.execute, Context([]), order)


@pytest.mark.asyncio
async def test_a_new_order_takes_the_catalogues_spelling_of_the_same_symbol() -> None:
    order = {"action": "sell", "volume": "0.01", "symbol": "xauusdM"}
    assert [r.symbol for r in await sent(trade.execute, Context([]), order)] == ["XAUUSDm"]


@pytest.mark.asyncio
async def test_closing_a_ticket_is_never_held_back_by_the_catalogue() -> None:
    # The broker still holds a position on a symbol its listing no longer returns.
    held = [position("7", "XAUUSD.old"), position("8", "XAUUSDm")]
    close = {"action": "close_position", "position_id": "7", "symbol": "XAUUSD.old"}
    assert [r.symbol for r in await sent(trade.execute, Context(held), close)] == ["XAUUSD.old"]
    by_symbol = await sent(trade.close_positions, Context(held), {"symbol": "XAUUSD.old"})
    assert [(r.position_id, r.symbol) for r in by_symbol] == [("7", "XAUUSD.old")]
    everything = await sent(trade.close_positions, Context(held), {})
    assert [r.position_id for r in everything] == ["7", "8"]


@pytest.mark.asyncio
async def test_closing_by_a_name_closes_only_that_exact_symbol_or_nothing() -> None:
    held = [position("8", "XAUUSDm"), position("9", "EURUSDm")]
    spelled = await sent(trade.close_positions, Context(held), {"symbol": "xauusdm"})
    assert [(r.position_id, r.symbol) for r in spelled] == [("8", "XAUUSDm")]
    # A code the account does not list closes nothing: the real symbol comes back instead.
    with pytest.raises(SymbolNotResolved) as failure:
        await sent(trade.close_positions, Context(held), {"symbol": "XAUUSD"})
    assert [item["symbol"] for item in failure.value.details["candidates"]] == ["XAUUSDm"]
