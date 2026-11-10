"""Exits stay possible on Alpaca: protected closes, re-armed protection, added protection.

Alpaca has no position-level stop. A bracket's exit legs (or an OCO / standalone stop
Lonora placed) hold the position's quantity, so a close first cancels them, waits until
the quantity is released, closes, and re-arms protection for whatever is still held. A
close that cannot run leaves the position protected; one that leaves it unprotected says
so (``protection.attention``) for the owner. Fake Alpaca server; no network.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from alpaca_fake import KEY_ID, SECRET_KEY, FakeAlpaca, Transport
from lonora_adapters.brokers import alpaca
from lonora_adapters.brokers.alpaca import AlpacaBroker
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError

AAPL = "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415"


class Harness:
    def __init__(self) -> None:
        self.fake = FakeAlpaca()
        self.transport = Transport(self.fake)
        self.sends = 0

    async def before_send(self) -> None:
        self.sends += 1


@pytest_asyncio.fixture
async def setup(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AlpacaBroker, Harness]]:
    harness = Harness()
    monkeypatch.setattr(alpaca, "transport_factory", lambda: harness.transport)
    monkeypatch.setattr(alpaca, "POLL_SECONDS", 0)
    broker = AlpacaBroker(KEY_ID, SECRET_KEY, "conn-1")
    yield broker, harness
    await broker.close()


def request(action: str, **fields: Any) -> TradeRequest:
    return TradeRequest.model_validate(
        {"account_id": "conn-1", "action": action, "symbol": "AAPL", **fields}
    )


async def send(broker: AlpacaBroker, harness: Harness, value: TradeRequest) -> TradeResult:
    return await broker.execute(value, harness.before_send)


async def protected(broker: AlpacaBroker, harness: Harness, qty: int = 10) -> None:
    opened = await send(
        broker,
        harness,
        request("buy", volume=qty, stop_loss=Decimal(220), take_profit=Decimal(240)),
    )
    assert opened.status == "confirmed"


def open_exits(harness: Harness) -> list[dict[str, Any]]:
    return [
        o
        for o in harness.fake.orders.values()
        if o["status"] in {"new", "accepted", "held", "pending_cancel"} and o["side"] == "sell"
    ]


async def the_position(broker: AlpacaBroker) -> Any:
    return next((p for p in await broker.positions() if p.id == AAPL), None)


@pytest.mark.asyncio
async def test_a_protected_close_cancels_the_legs_then_closes(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert result.status == "confirmed", result
    assert harness.sends == 2  # one boundary per operation, however many steps follow
    steps = [step["step"] for step in result.details["protection"]["steps"]]
    assert steps.count("cancel") == 2 and steps.index("close") > 1
    assert steps[-1] == "restore"  # nothing left to protect
    assert result.details["protection"]["restored"] is True
    assert result.details["protection"]["attention"] is False
    assert await the_position(broker) is None and open_exits(harness) == []


@pytest.mark.asyncio
async def test_a_partial_close_re_arms_the_rest_at_the_same_levels(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    result = await send(broker, harness, request("close_position", position_id=AAPL, volume=4))
    assert result.status == "confirmed", result
    assert result.details["protection"]["restored"] is True
    position = await the_position(broker)
    assert position.volume == Decimal(6)
    assert (position.stop_loss, position.take_profit) == (Decimal(220), Decimal(240))
    assert {Decimal(o["qty"]) for o in open_exits(harness)} == {Decimal(6)}
    assert all(
        o["client_order_id"].startswith("LNP_") or o.get("group_role") for o in open_exits(harness)
    )


@pytest.mark.asyncio
async def test_released_quantity_is_waited_for_within_a_bound(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    harness.fake.cancel_polls = 3
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert result.status == "confirmed", result
    assert await the_position(broker) is None


@pytest.mark.asyncio
async def test_quantity_never_released_sends_no_close_and_re_arms(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    harness.fake.cancel_polls = 10_000
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert (result.status, result.code) == ("failed", "broker_protection_cancel_failed"), result
    assert ("DELETE", f"/v2/positions/{AAPL}") not in harness.fake.mutations
    assert result.details["protection"]["attention"] is True


@pytest.mark.asyncio
async def test_a_refused_leg_cancel_sends_no_close_and_the_position_stays_protected(
    setup: Any,
) -> None:
    broker, harness = setup
    await protected(broker, harness)
    first = next(o for o in harness.fake.orders.values() if o.get("group_role") == "take_profit")
    harness.fake.fail_next[f"DELETE /v2/orders/{first['id']}"] = (500, 50010000, "internal error")
    harness.fake.fail_next[f"DELETE /v2/orders/{_stop(harness)['id']}"] = (
        500,
        50010000,
        "internal error",
    )
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert (result.status, result.code) == ("failed", "broker_protection_cancel_failed"), result
    assert ("DELETE", f"/v2/positions/{AAPL}") not in harness.fake.mutations
    position = await the_position(broker)
    assert (position.volume, position.stop_loss, position.take_profit) == (
        Decimal(10),
        Decimal(220),
        Decimal(240),
    )
    assert result.details["protection"]["restored"] is True


def _stop(harness: Harness) -> dict[str, Any]:
    return next(
        o
        for o in harness.fake.orders.values()
        if o.get("group_role") == "stop_loss" and o["status"] in {"new", "held"}
    )


@pytest.mark.asyncio
async def test_a_close_refused_after_the_cancel_restores_protection_and_alerts(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    harness.fake.fail_next[f"DELETE /v2/positions/{AAPL}"] = (403, 40310000, "trade denied")
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert (result.status, result.code) == ("failed", "broker_request_rejected"), result
    assert result.details["protection"]["restored"] is True
    assert result.details["protection"]["attention"] is True
    position = await the_position(broker)
    assert (position.volume, position.stop_loss, position.take_profit) == (
        Decimal(10),
        Decimal(220),
        Decimal(240),
    )


@pytest.mark.asyncio
async def test_protection_that_cannot_be_restored_is_reported(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    harness.fake.fail_next[f"DELETE /v2/positions/{AAPL}"] = (403, 40310000, "trade denied")
    harness.fake.fail_next["POST /v2/orders"] = (403, 40310000, "trade denied")
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert result.status == "failed"
    assert result.details["protection"]["restored"] is False
    assert result.details["protection"]["attention"] is True
    assert (await the_position(broker)).stop_loss is None


@pytest.mark.asyncio
async def test_an_unknown_close_outcome_never_re_arms(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    harness.transport.lose_after.add(f"DELETE /v2/positions/{AAPL}")
    result = await send(broker, harness, request("close_position", position_id=AAPL))
    assert result.status == "ambiguous", result
    assert result.details["protection"]["attention"] is True
    # A sell stop with nothing held would open a short: nothing was re-armed.
    assert open_exits(harness) == []


@pytest.mark.asyncio
async def test_protection_is_added_to_an_unprotected_position(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, request("buy", volume=10))
    stop_only = await send(
        broker, harness, request("modify_position", position_id=AAPL, stop_loss=Decimal(221))
    )
    assert stop_only.status == "confirmed", stop_only
    position = await the_position(broker)
    assert (position.stop_loss, position.take_profit) == (Decimal(221), None)
    assert await broker.orders() == []  # protection is not a pending entry
    tighten = request("modify_position", position_id=AAPL, stop_loss=Decimal(225))
    assert (await send(broker, harness, tighten)).status == "confirmed"
    assert (await the_position(broker)).stop_loss == Decimal(225)
    closed = await send(broker, harness, request("close_position", position_id=AAPL))
    assert closed.status == "confirmed" and await the_position(broker) is None
    reconciled = await broker.reconcile(
        stop_only.operation_id,
        request(
            "modify_position",
            position_id=AAPL,
            stop_loss=Decimal(221),
            operation_id=stop_only.operation_id,
        ),
    )
    assert reconciled.status == "confirmed"  # found by its protection client order id


@pytest.mark.asyncio
async def test_both_levels_are_added_as_one_oco(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, request("buy", volume=10))
    both = request(
        "modify_position", position_id=AAPL, stop_loss=Decimal(221), take_profit=Decimal(245)
    )
    assert (await send(broker, harness, both)).status == "confirmed"
    position = await the_position(broker)
    assert (position.stop_loss, position.take_profit) == (Decimal(221), Decimal(245))
    assert {o["order_class"] for o in open_exits(harness)} == {"oco"}


@pytest.mark.asyncio
async def test_widening_edits_stay_refused_before_send(setup: Any) -> None:
    broker, harness = setup
    await protected(broker, harness)
    sends = harness.sends
    clear = request("modify_position", position_id=AAPL, clear_stop_loss=True)
    with pytest.raises(LonoraError) as refused:
        await send(broker, harness, clear)
    assert refused.value.code == "broker_protection_clear_unsupported"
    assert harness.sends == sends
