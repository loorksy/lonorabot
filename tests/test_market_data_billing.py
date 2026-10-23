"""Provider billing is separate from broker streams; no network or money effects."""

import asyncio
import importlib
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_adapters.brokers import metaapi
from lonora_adapters.brokers.metaapi import MetaApiBroker, provider_error
from lonora_core.user_error import LonoraError

BILLING_MESSAGE = "To allow market data access please top up your account., check error.details for more information."


class ProviderFailure(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status_code = status


def broker_with_history(history: Any) -> MetaApiBroker:
    broker = object.__new__(MetaApiBroker)
    broker.account_id = "fixture-account"
    broker.connection_id = "fixture-connection"
    broker.account_lock = asyncio.Lock()
    broker.account_instance = SimpleNamespace(get_historical_candles=history)
    return broker


def bars(symbol: str = "EURUSDm", timeframe: str = "1m") -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "time": "2026-10-23T00:00:00Z",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
        }
    ]


@pytest.mark.parametrize("status", [400, 402])
def test_precise_history_payment_condition(status: int):
    error = ProviderFailure(BILLING_MESSAGE, status)
    assert provider_error(error, "candles").code == "broker_market_data_billing_required"
    assert provider_error(error, "rpc").code != "broker_market_data_billing_required"


def test_actual_pinned_sdk_validation_exception_keeps_the_billing_cause():
    sdk: Any = importlib.import_module("metaapi_cloud_sdk.clients.error_handler")
    error = sdk.ValidationException(
        BILLING_MESSAGE,
        details=[{"message": "Account requires a provider top-up"}],
        url="https://example.test/historical-market-data?token=private-fixture",
    )
    assert error.status_code == 400
    assert provider_error(error, "candles").code == "broker_market_data_billing_required"


@pytest.mark.parametrize(
    "message,status",
    [
        ("Symbol not found", 404),
        ("Invalid timeframe", 400),
        ("Unrecognized account", 400),
        ("top up", 400),
        ("Invalid request. Request URL: " + BILLING_MESSAGE, 400),
        (BILLING_MESSAGE, 401),
    ],
)
def test_unrelated_errors_never_become_billing(message: str, status: int):
    assert (
        provider_error(ProviderFailure(message, status), "candles").code
        != "broker_market_data_billing_required"
    )


@pytest.mark.asyncio
async def test_cooldown_covers_symbols_and_preserves_stream_and_rpc(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [1000.0]
    monkeypatch.setattr(metaapi, "monotonic", lambda: clock[0])
    historical = AsyncMock(side_effect=ProviderFailure(BILLING_MESSAGE))
    broker = broker_with_history(historical)
    stream, rpc = object(), object()
    broker.streaming, broker.rpc = stream, rpc
    with pytest.raises(LonoraError, match="broker_market_data_billing_required"):
        await broker.candles("EURUSDm", "1m", 100)
    for symbol, timeframe in [("XAUUSD.a", "15m"), ("US500.cash", "4h"), ("BTCUSD#", "1d")]:
        with pytest.raises(LonoraError, match="broker_market_data_billing_required"):
            await broker.candles(symbol, timeframe, 100)
    assert historical.await_count == 1
    assert broker.streaming is stream and broker.rpc is rpc
    assert vars(broker)["_history_billing_retry_at"] == 1300
    clock[0] = 1300.0
    historical.side_effect = None
    historical.return_value = bars("BTCUSD#", "1d")
    assert (await broker.candles("BTCUSD#", "1d", 100))[0].symbol == "BTCUSD#"
    assert vars(broker)["_history_billing_failure"] is None
    historical.return_value = bars()
    assert len(await broker.candles("EURUSDm", "1m", 100)) == 1
    assert historical.await_count == 3


@pytest.mark.asyncio
async def test_one_recovery_probe_and_cancelled_probe_does_not_storm(
    monkeypatch: pytest.MonkeyPatch,
):
    clock = [1000.0]
    monkeypatch.setattr(metaapi, "monotonic", lambda: clock[0])
    historical = AsyncMock(side_effect=ProviderFailure(BILLING_MESSAGE))
    broker = broker_with_history(historical)
    with pytest.raises(LonoraError):
        await broker.candles("EURUSDm", "1m", 100)
    clock[0] = 1301
    started, finish = asyncio.Event(), asyncio.Event()

    async def probe(**kwargs: Any):
        started.set()
        await finish.wait()
        return bars()

    historical.side_effect = probe
    task = asyncio.create_task(broker.candles("EURUSDm", "1m", 100))
    await started.wait()
    for _ in range(10):
        with pytest.raises(LonoraError, match="broker_market_data_billing_required"):
            await broker.candles("XAUUSDm", "15m", 100)
    assert historical.await_count == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not vars(broker)["_history_billing_probe"]
    with pytest.raises(LonoraError, match="broker_market_data_billing_required"):
        await broker.candles("US500.cash", "4h", 100)
    assert historical.await_count == 2
    clock[0] = 1602
    finish.set()
    assert len(await broker.candles("EURUSDm", "1m", 100)) == 1
    assert historical.await_count == 3


@pytest.mark.asyncio
async def test_healthy_distinct_histories_remain_concurrent():
    started = 0
    all_started = asyncio.Event()

    async def historical(**kwargs: Any):
        nonlocal started
        started += 1
        if started == 4:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), 1)
        return bars(kwargs["symbol"], kwargs["timeframe"])

    history = AsyncMock(side_effect=historical)
    broker = broker_with_history(history)
    rows = await asyncio.gather(
        *[
            broker.candles(symbol, timeframe, 100)
            for symbol, timeframe in [
                ("EURUSDm", "1m"),
                ("XAUUSD.a", "15m"),
                ("US500.cash", "4h"),
                ("BTCUSD#", "1d"),
            ]
        ]
    )
    assert len(rows) == history.await_count == 4
    assert vars(broker)["_history_billing_failure"] is None


@pytest.mark.asyncio
async def test_sync_timeout_is_not_hidden_as_provider_billing():
    history = AsyncMock(side_effect=TimeoutError("waitSynchronized timed out"))
    broker = broker_with_history(history)
    with pytest.raises(LonoraError, match="broker_candles_timeout"):
        await broker.candles("EURUSDm", "1m", 100)
    assert getattr(broker, "_history_billing_failure", None) is None


@pytest.mark.asyncio
async def test_live_price_stays_readable_while_candle_billing_is_blocked():
    historical = AsyncMock(side_effect=ProviderFailure(BILLING_MESSAGE))
    broker = broker_with_history(historical)
    live = {
        "symbol": "XAUUSDm",
        "bid": "100",
        "ask": "101",
        "time": datetime.now(UTC),
    }

    def price(symbol: str) -> dict[str, Any]:
        assert symbol == "XAUUSDm"
        return live

    broker.streaming = SimpleNamespace(
        _closed=False,
        _meta_api_connection=SimpleNamespace(synchronized=True),
        terminal_state=SimpleNamespace(price=price),
    )
    rpc = AsyncMock(side_effect=AssertionError("working live price must not require RPC"))
    broker.read_rpc = rpc
    with pytest.raises(LonoraError, match="broker_market_data_billing_required"):
        await broker.candles("XAUUSDm", "1m", 100)
    quote = await broker.quote("XAUUSDm")
    assert quote.symbol == "XAUUSDm" and quote.bid == 100
    assert historical.await_count == 1
    rpc.assert_not_awaited()
