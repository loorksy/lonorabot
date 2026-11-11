"""A new order names the account's exact symbol; an exit is never held back by the catalogue."""

from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
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

    def __init__(self, positions: list[Position], symbols: Any = None, recorded: Any = None):
        @asynccontextmanager
        async def sessions():
            yield SimpleNamespace(get=AsyncMock(return_value=recorded))

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


def contract(minimum: str = "0.01", maximum: str = "200", step: str = "0.01") -> Any:
    specification = SimpleNamespace(
        volume_min=Decimal(minimum), volume_max=Decimal(maximum), volume_step=Decimal(step)
    )
    return SimpleNamespace(instrument=AsyncMock(return_value=specification))


@pytest.mark.asyncio
async def test_a_size_the_contract_cannot_take_is_refused_with_its_limits() -> None:
    """[X_args] 0.001 lot of gold: nothing is sent and the model is given the minimum."""
    from lonora_core.user_error import ToolRefusal

    with pytest.raises(ToolRefusal) as small:
        await trade.require_order_size(contract(), "XAUUSDm", "0.001")
    assert small.value.code == "volume_out_of_range"
    assert small.value.details["class"] == "input" and not small.value.details["retryable"]
    assert small.value.details["limits"] == {
        "volume_min": "0.01",
        "volume_max": "200",
        "volume_step": "0.01",
    }
    assert "0.01" in small.value.details["hint"]
    with pytest.raises(ToolRefusal) as uneven:
        await trade.require_order_size(contract(step="0.1", minimum="0.1"), "XAUUSDm", "0.15")
    assert uneven.value.code == "volume_step_mismatch"
    await trade.require_order_size(contract(), "XAUUSDm", "0.02")
    await trade.require_order_size(contract(), "XAUUSDm", Decimal("200"))


@pytest.mark.asyncio
async def test_an_unreadable_specification_leaves_the_size_to_the_executor() -> None:
    unreadable = SimpleNamespace(instrument=AsyncMock(side_effect=ConnectionError()))
    await trade.require_order_size(unreadable, "XAUUSDm", "0.001")
    await trade.require_order_size(contract(), "XAUUSDm", "not a number")


@pytest.mark.asyncio
async def test_only_a_new_order_has_its_size_checked_before_the_executor() -> None:
    context = Context([position("7", "XAUUSDm")])
    broker = await context.brokers.get("owner", "account")
    broker.instrument = contract().instrument
    from lonora_core.user_error import ToolRefusal

    order = {"account_id": "account", "symbol": "XAUUSDm", "action": "buy", "volume": "0.001"}
    with pytest.raises(ToolRefusal):
        await sent(trade.execute, context, order)
    # A partial close names its ticket: an exit is never held back here.
    closing = {**order, "action": "close_position", "position_id": "7"}
    assert [r.volume for r in await sent(trade.execute, context, closing)] == [Decimal("0.001")]


@pytest.mark.asyncio
async def test_a_call_that_already_has_a_record_is_never_checked_again() -> None:
    """After approval, a restart or an unknown outcome the record answers, not a new check."""
    context = Context([], recorded=SimpleNamespace(status="approved"))
    broker = await context.brokers.get("owner", "account")
    broker.instrument = contract(minimum="1").instrument
    order = {"account_id": "account", "symbol": "XAUUSDm", "action": "buy", "volume": "0.01"}
    assert [r.volume for r in await sent(trade.execute, context, order)] == [Decimal("0.01")]
    broker.instrument.assert_not_awaited()


def managing(position_id: str, symbol: str = "XAUUSDm", **extra: Any) -> TradeRequest:
    return TradeRequest(
        operation_id="op-" + position_id,
        account_id="account",
        symbol=symbol,
        action="close_position",
        position_id=position_id,
        **extra,
    )


@pytest.mark.asyncio
async def test_a_ticket_the_account_does_not_hold_is_refused_with_those_it_does() -> None:
    from lonora_tools.resolve import NotResolved

    context = Context([position("7", "XAUUSDm"), position("8", "EURUSDm")])
    request = managing("wrong")
    with pytest.raises(NotResolved) as one:
        await trade.require_tickets(
            cast(Any, context), [request], {trade.target_key(request): None}
        )
    assert one.value.code == "position_not_found" and one.value.details["retryable"] is True
    assert one.value.details["candidates"] == [
        {
            "id": "7",
            "label": "XAUUSDm",
            "symbol": "XAUUSDm",
            "side": "buy",
            "volume": "0.01",
            "open_price": "4100",
            "profit": "0",
        }
    ]
    # The next call names the real ticket; nothing was put in the place of the one named.
    assert one.value.details["next_actions"] == [{"repeat_with": {"position_id": "7"}}]
    two = Context([position("7", "XAUUSDm"), position("9", "XAUUSDm")])
    with pytest.raises(NotResolved) as several:
        await trade.require_tickets(cast(Any, two), [request], {trade.target_key(request): None})
    assert several.value.code == "position_ambiguous"
    assert [item["id"] for item in several.value.details["candidates"]] == ["7", "9"]
    other = managing("wrong", "GBPUSDm")
    with pytest.raises(NotResolved) as none:
        await trade.require_tickets(cast(Any, context), [other], {trade.target_key(other): None})
    assert none.value.details["candidates"] == []
    assert [item["id"] for item in none.value.details["existing"]] == ["7", "8"]


@pytest.mark.asyncio
async def test_a_held_ticket_a_recorded_call_and_an_unreadable_account_are_never_checked() -> None:
    request = managing("7")
    held = Context([position("7", "XAUUSDm")])
    broker = await held.brokers.get("owner", "account")
    await trade.require_tickets(
        cast(Any, held), [request], {trade.target_key(request): {"volume": "0.01"}}
    )
    broker.positions.assert_not_awaited()
    # After approval, a restart or an unknown outcome the record answers: the position
    # may be gone because the first attempt closed it.
    gone = managing("closed-already")
    recorded = Context([], recorded=SimpleNamespace(status="completed"))
    await trade.require_tickets(cast(Any, recorded), [gone], {trade.target_key(gone): None})
    unreadable = Context([])
    (await unreadable.brokers.get("owner", "account")).positions = AsyncMock(
        side_effect=ConnectionError()
    )
    await trade.require_tickets(cast(Any, unreadable), [gone], {trade.target_key(gone): None})
