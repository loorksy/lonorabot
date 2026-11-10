"""Alpaca paper adapter against the local fake Alpaca server. No network, no live host."""

import logging
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from alpaca_fake import KEY_ID, SECRET_KEY, FakeAlpaca, Transport
from lonora_adapters.brokers import alpaca
from lonora_adapters.brokers.alpaca import (
    AlpacaBroker,
    client_order_id,
    credentials_from_secret,
    credentials_secret,
)
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError

AAPL_ID = "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415"
BTC_ID = "276e2673-764b-4ab6-a611-caf665ca6340"


class Harness:
    def __init__(self) -> None:
        self.fake = FakeAlpaca()
        self.transport = Transport(self.fake)
        self.sends = 0
        self.mutations_at_send: list[int] = []

    async def before_send(self) -> None:
        # The boundary is crossed before any broker mutation exists.
        self.sends += 1
        self.mutations_at_send.append(len(self.fake.mutations))


@pytest_asyncio.fixture
async def setup(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AlpacaBroker, Harness]]:
    harness = Harness()
    monkeypatch.setattr(alpaca, "transport_factory", lambda: harness.transport)
    broker = AlpacaBroker(KEY_ID, SECRET_KEY, "conn-1")
    yield broker, harness
    await broker.close()


def entry(action: str = "buy", symbol: str = "AAPL", **fields: Any) -> TradeRequest:
    fields.setdefault("volume", Decimal(10))
    return TradeRequest.model_validate(
        {"account_id": "conn-1", "action": action, "symbol": symbol, **fields}
    )


async def send(broker: AlpacaBroker, harness: Harness, request: TradeRequest) -> TradeResult:
    return await broker.execute(request, harness.before_send)


def test_both_keys_rest_as_one_secret_and_partial_keys_are_refused() -> None:
    stored = credentials_secret(" PKID ", "secret")
    assert credentials_from_secret(stored) == ("PKID", "secret")
    for bad in ("", "not json", "[]", '{"key_id": "x"}'):
        with pytest.raises(LonoraError):
            credentials_from_secret(bad)
    with pytest.raises(LonoraError):
        credentials_secret("PKID", " ")


@pytest.mark.asyncio
async def test_paper_hosts_only_and_live_or_foreign_hosts_are_refused(setup: Any) -> None:
    broker, harness = setup
    await broker.account()
    await broker.quote("AAPL")
    assert harness.fake.seen_hosts == {"paper-api.alpaca.markets", "data.alpaca.markets"}
    with pytest.raises(LonoraError) as refused:
        await broker.request("GET", "https://api.alpaca.markets", "/v2/account")
    assert refused.value.code == "broker_endpoint_forbidden"
    assert alpaca.TRADING_URL == "https://paper-api.alpaca.markets"


@pytest.mark.asyncio
async def test_account_identity_and_currency(setup: Any) -> None:
    broker, _ = setup
    account = await broker.account()
    assert account.id == "conn-1" and account.currency == "USD"
    assert (account.login, account.server, account.platform) == (
        "PA3TEST00001",
        "paper-api.alpaca.markets",
        "alpaca",
    )
    assert account.balance == Decimal(100000) and account.trade_allowed is True
    assert account.free_margin == account.equity - account.margin
    identity = await broker.metadata_identity()
    assert identity["login"] == "PA3TEST00001" and identity["broker"] == "Alpaca"


@pytest.mark.asyncio
async def test_catalog_lists_tradable_stocks_and_crypto_with_their_increments(setup: Any) -> None:
    broker, _ = setup
    symbols = await broker.symbols()
    assert symbols == ["AAPL", "BTC/USD", "ETH/BTC", "TSLA"]  # untradable GBTC.OLD is absent
    stock = await broker.instrument("AAPL")
    assert (stock.tick_size, stock.volume_min, stock.volume_step) == (
        Decimal("0.01"),
        Decimal(1),
        Decimal(1),
    )
    btc = await broker.instrument("BTC/USD")
    assert (btc.tick_size, btc.volume_min, btc.volume_step, btc.digits) == (
        Decimal(1),
        Decimal("0.0001"),
        Decimal("0.000000001"),
        0,
    )
    assert (btc.base_currency, btc.profit_currency) == ("BTC", "USD")
    with pytest.raises(LonoraError) as missing:
        await broker.instrument("NOPE")
    assert missing.value.code == "symbol_not_found"


@pytest.mark.asyncio
async def test_quotes_carry_tick_value_only_in_the_account_currency(setup: Any) -> None:
    broker, _ = setup
    quote = await broker.quote("AAPL")
    assert (quote.bid, quote.ask, quote.source) == (Decimal("230.1"), Decimal("230.15"), "alpaca")
    assert quote.loss_tick_value == Decimal("0.01")
    assert quote.tick_value_basis == "account_currency_per_lot"
    crypto = await broker.quote("BTC/USD")
    assert crypto.loss_tick_value == Decimal(1)
    # Quoted in BTC: P&L is not account money, so no tick value is claimed.
    cross = await broker.quote("ETH/BTC")
    assert cross.loss_tick_value is None and cross.tick_value_basis is None
    with pytest.raises(LonoraError) as empty:
        await broker.quote("TSLA")  # an empty ask side is no executable price
    assert empty.value.code == "quote_unavailable"


@pytest.mark.asyncio
async def test_candles_are_exact_broker_bars_in_time_order(setup: Any) -> None:
    broker, harness = setup
    bars = await broker.candles("AAPL", "1h", 3)
    assert [bar.close for bar in bars] == [Decimal(231), Decimal(232), Decimal(233)]
    assert all(bar.symbol == "AAPL" and bar.timeframe == "1h" for bar in bars)
    assert bars == sorted(bars, key=lambda bar: bar.time)
    assert len(await broker.candles("BTC/USD", "5m", 1000)) == 5
    assert ("GET", "/v1beta3/crypto/us/bars") in harness.fake.requests
    with pytest.raises(LonoraError):
        await broker.candles("AAPL", "7m", 3)


@pytest.mark.asyncio
async def test_bracket_entry_sends_once_after_the_boundary_and_reads_back_protection(
    setup: Any,
) -> None:
    broker, harness = setup
    request = entry(stop_loss=Decimal(220), take_profit=Decimal(240))
    result = await send(broker, harness, request)
    assert result.status == "confirmed" and result.details["position_id"] == AAPL_ID
    assert result.details["price"] == "230.15" and result.details["environment"] == "paper"
    assert harness.sends == 1 and harness.mutations_at_send == [0]
    assert harness.fake.mutations == [("POST", "/v2/orders")]
    placed = next(iter(harness.fake.orders.values()))
    assert placed["client_order_id"] == client_order_id(request.operation_id)
    assert placed["order_class"] == "bracket" and placed["time_in_force"] == "day"
    (position,) = await broker.positions()
    assert (position.id, position.side, position.volume) == (AAPL_ID, "buy", Decimal(10))
    assert (position.stop_loss, position.take_profit) == (Decimal(220), Decimal(240))
    assert await broker.orders() == []  # exit legs are protection, not pending entries


@pytest.mark.asyncio
async def test_refusals_before_the_boundary_send_nothing(setup: Any) -> None:
    broker, harness = setup
    cases = [
        (
            entry("buy_stop", "BTC/USD", volume=1, price=Decimal(80000)),
            "broker_order_type_unsupported",
        ),
        (
            entry("buy", "BTC/USD", volume=1, stop_loss=Decimal(60000)),
            "broker_protection_unsupported",
        ),
        (entry("buy", "NOPE"), "symbol_not_found"),
    ]
    for request, code in cases:
        with pytest.raises(LonoraError) as refused:
            await send(broker, harness, request)
        assert refused.value.code == code
    harness.fake.is_open = False
    with pytest.raises(LonoraError) as closed:
        await send(broker, harness, entry())
    assert closed.value.code == "market_closed"
    # A pending stock order and crypto do not need the session.
    assert (
        await send(broker, harness, entry("buy_limit", price=Decimal(200)))
    ).status == "confirmed"
    assert (await send(broker, harness, entry("buy", "BTC/USD", volume=1))).status == "confirmed"
    assert harness.sends == 2 and len(harness.fake.mutations) == 2


@pytest.mark.asyncio
async def test_lost_response_is_ambiguous_and_reconciles_by_client_order_id(setup: Any) -> None:
    broker, harness = setup
    request = entry()
    harness.transport.lose_after.add("POST /v2/orders")
    lost = await send(broker, harness, request)
    assert (lost.status, lost.code) == ("ambiguous", "broker_result_ambiguous")
    found = await broker.reconcile(request.operation_id, request)
    assert found.status == "confirmed" and found.details["reconciled"] is True
    assert found.details["position_id"] == AAPL_ID
    never = entry()
    harness.transport.lose_before.add("POST /v2/orders")
    assert (await send(broker, harness, never)).status == "ambiguous"
    missing = await broker.reconcile(never.operation_id, never)
    assert (missing.status, missing.code) == ("ambiguous", "execution_not_observed")
    # A different symbol under the same identity is not this operation.
    other = entry(symbol="TSLA", operation_id=request.operation_id)
    assert (await broker.reconcile(request.operation_id, other)).status == "ambiguous"


@pytest.mark.asyncio
async def test_received_refusals_are_failed_and_server_faults_stay_ambiguous(setup: Any) -> None:
    broker, harness = setup
    poor = await send(broker, harness, entry(volume=100000))
    assert (poor.status, poor.code) == ("failed", "broker_request_rejected")
    assert poor.details["http_status"] == 403 and "buying power" in poor.details["description"]
    harness.fake.fail_next["POST /v2/orders"] = (500, 50010000, "internal error")
    fault = await send(broker, harness, entry())
    assert (fault.status, fault.code) == ("ambiguous", "broker_result_ambiguous")
    harness.fake.fail_next["POST /v2/orders"] = (429, 42910000, "rate limit exceeded")
    limited = await send(broker, harness, entry())
    assert (limited.status, limited.code) == ("failed", "broker_rate_limited")
    duplicate = entry()
    assert (await send(broker, harness, duplicate)).status == "confirmed"
    again = await send(broker, harness, duplicate)
    assert again.status == "ambiguous"  # an existing identity is never read as "not sent"
    short = await send(broker, harness, entry("sell", "BTC/USD", volume=1))
    assert (short.status, short.code) == ("failed", "broker_request_rejected")


@pytest.mark.asyncio
async def test_read_errors_map_into_the_broker_taxonomy(setup: Any, monkeypatch: Any) -> None:
    broker, harness = setup
    harness.fake.fail_next["GET /v2/account"] = (429, 42910000, "rate limit exceeded")
    with pytest.raises(LonoraError) as limited:
        await broker.account()
    assert limited.value.code == "broker_rate_limited"
    harness.transport.lose_before.add("GET /v2/positions")
    with pytest.raises(LonoraError) as timeout:
        await broker.positions()
    assert timeout.value.code == "broker_connection_timeout"
    rejected = AlpacaBroker(KEY_ID, "wrong-secret", "conn-2")
    with pytest.raises(LonoraError) as credentials:
        await rejected.account()
    assert credentials.value.code == "broker_credentials_rejected"
    await rejected.close()


@pytest.mark.asyncio
async def test_protection_edit_replaces_exactly_one_leg(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, entry(stop_loss=Decimal(220), take_profit=Decimal(240)))
    tighten = TradeRequest(
        account_id="conn-1",
        action="modify_position",
        symbol="AAPL",
        position_id=AAPL_ID,
        stop_loss=Decimal(225),
        take_profit=Decimal(240),  # unchanged: only one leg is edited
    )
    result = await send(broker, harness, tighten)
    assert result.status == "confirmed" and harness.fake.mutations[-1][0] == "PATCH"
    (position,) = await broker.positions()
    assert (position.stop_loss, position.take_profit) == (Decimal(225), Decimal(240))
    sends = harness.sends
    both = tighten.model_copy(update={"stop_loss": Decimal(226), "take_profit": Decimal(245)})
    clear = TradeRequest(
        account_id="conn-1",
        action="modify_position",
        symbol="AAPL",
        position_id=AAPL_ID,
        clear_take_profit=True,
    )
    for request, code in (
        (both, "broker_protection_edit_one_at_a_time"),
        (clear, "broker_protection_clear_unsupported"),
    ):
        with pytest.raises(LonoraError) as refused:
            await send(broker, harness, request)
        assert refused.value.code == code
    assert harness.sends == sends
    reconciled = await broker.reconcile(tighten.operation_id, tighten)
    assert (reconciled.status, reconciled.code) == ("ambiguous", "mutation_evidence_required")


@pytest.mark.asyncio
async def test_unprotected_position_has_no_leg_to_edit(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, entry())
    request = TradeRequest(
        account_id="conn-1",
        action="modify_position",
        symbol="AAPL",
        position_id=AAPL_ID,
        stop_loss=Decimal(225),
    )
    with pytest.raises(LonoraError) as refused:
        await send(broker, harness, request)
    assert refused.value.code == "broker_protection_leg_missing" and harness.sends == 1


@pytest.mark.asyncio
async def test_pending_order_modify_and_cancel(setup: Any) -> None:
    broker, harness = setup
    placed = await send(broker, harness, entry("sell_limit", price=Decimal(250), volume=5))
    (order,) = await broker.orders()
    assert (order.id, order.side, order.price, order.volume) == (
        placed.broker_id,
        "sell_limit",
        Decimal(250),
        Decimal(5),
    )
    moved = await send(
        broker,
        harness,
        TradeRequest(
            account_id="conn-1",
            action="modify_order",
            symbol="AAPL",
            order_id=order.id,
            price=Decimal(255),
        ),
    )
    assert moved.status == "confirmed" and moved.broker_id != order.id
    assert moved.details["replaced_order_id"] == order.id
    (replacement,) = await broker.orders()
    assert replacement.price == Decimal(255)
    cancel = TradeRequest(
        account_id="conn-1", action="cancel_order", symbol="AAPL", order_id=replacement.id
    )
    assert (await send(broker, harness, cancel)).status == "confirmed"
    assert await broker.orders() == []
    with pytest.raises(LonoraError) as gone:
        await send(broker, harness, cancel.model_copy(update={"operation_id": "again"}))
    assert gone.value.code == "order_not_found"


@pytest.mark.asyncio
async def test_closes_full_partial_and_held_by_protection(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, entry("buy", "BTC/USD", volume=2))
    partial = TradeRequest(
        account_id="conn-1",
        action="close_position",
        symbol="BTC/USD",
        position_id=BTC_ID,
        volume=Decimal("0.5"),
    )
    result = await send(broker, harness, partial)
    assert result.status == "confirmed" and result.details["volume"] == "0.5"
    assert harness.fake.mutations[-1] == ("DELETE", f"/v2/positions/{BTC_ID}")
    (position,) = await broker.positions()
    assert position.symbol == "BTC/USD" and position.volume == Decimal("1.5")
    full = partial.model_copy(update={"operation_id": "full", "volume": None})
    assert (await send(broker, harness, full)).status == "confirmed"
    assert await broker.positions() == []
    # A protected stock position: Alpaca holds its quantity for the exit legs.
    await send(broker, harness, entry(stop_loss=Decimal(220), take_profit=Decimal(240)))
    held = TradeRequest(
        account_id="conn-1", action="close_position", symbol="AAPL", position_id=AAPL_ID
    )
    refused = await send(broker, harness, held)
    assert (refused.status, refused.code) == ("failed", "broker_request_rejected")
    assert "insufficient qty" in refused.details["description"]
    lost = await broker.reconcile(held.operation_id, held)
    assert (lost.status, lost.code) == ("ambiguous", "execution_not_observed")
    with pytest.raises(LonoraError) as missing:
        await send(
            broker, harness, held.model_copy(update={"position_id": "nope", "operation_id": "x"})
        )
    assert missing.value.code == "position_not_found"


@pytest.mark.asyncio
async def test_history_lists_fills(setup: Any) -> None:
    broker, harness = setup
    await send(broker, harness, entry("buy", "BTC/USD", volume=1))
    from datetime import UTC, datetime, timedelta

    rows = await broker.history(datetime.now(UTC) - timedelta(days=1), datetime.now(UTC), 10)
    assert rows[0]["symbol"] == "BTC/USD" and rows[0]["type"] == "buy"


@pytest.mark.asyncio
async def test_keys_never_reach_results_diagnostics_or_logs(
    setup: Any, caplog: pytest.LogCaptureFixture
) -> None:
    broker, harness = setup
    caplog.set_level(logging.DEBUG)
    results = [await send(broker, harness, entry(volume=100000))]
    harness.fake.fail_next["POST /v2/orders"] = (
        422,
        40010001,
        f"bad request for key {KEY_ID} and {SECRET_KEY}",
    )
    results.append(await send(broker, harness, entry()))
    try:
        await AlpacaBroker(KEY_ID, "wrong", "c").account()
    except LonoraError as error:
        assert KEY_ID not in str(error.diagnostic_message)
    text = caplog.text + "".join(result.model_dump_json() for result in results)
    assert KEY_ID not in text and SECRET_KEY not in text
    assert "[redacted]" in text or "bad request" in text
