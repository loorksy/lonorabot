"""SDK29.1.1 conformance: native historical REST, independent RPC, safe diagnostics. No live calls."""

import asyncio
import importlib
import logging
from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_core.chart_controller import TIMEFRAMES
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError


async def main() -> None:
    errors: Any = importlib.import_module("metaapi_cloud_sdk.clients.error_handler")
    sdk_account_type: Any = importlib.import_module(
        "metaapi_cloud_sdk.metaapi.metatrader_account"
    ).MetatraderAccount
    calls: list[tuple[str, str, str, str, Any, int]] = []
    mode = "normal"

    async def historical(
        account_id: str, region: str, symbol: str, timeframe: str, start: Any, limit: int
    ) -> list[dict[str, Any]]:
        calls.append((account_id, region, symbol, timeframe, start, limit))
        if mode == "timeout":
            raise TimeoutError(
                "Historical REST timed out using tinyTok at https://user:pass@host/path?auth-token=tinyTok"
            )
        if mode == "credentials":
            raise errors.UnauthorizedException(
                "Authorization: Basic dXNlcjpwdw==; token=tinyTok",
                "https://host/accounts/account-fixture",
            )
        if mode == "account_deleted":
            raise errors.NotFoundException(
                "Account not found", "https://host/accounts/account-fixture/symbols/ABC"
            )
        if mode == "generic_404":
            raise errors.NotFoundException(
                "Endpoint not found", "https://host/accounts/account-fixture/symbols/ABC"
            )
        if symbol == "UNKNOWN.a":
            raise errors.NotFoundException(
                "Symbol not found",
                "https://host/accounts/account-fixture/symbols/UNKNOWN.a?token=tinyTok",
            )
        if symbol == "EMPTY.a":
            return []
        return [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "time": "2026-10-14T00:00:00Z",
                "open": 100,
                "high": 110 if mode != "invalid_ohlc" else 90,
                "low": 95,
                "close": 105,
            }
        ]

    # Exercise the real SDK account method and region property, not a replica.
    account: Any = object.__new__(sdk_account_type)
    account._data = {"_id": "account-fixture", "region": "london"}
    account._historical_market_data_client = SimpleNamespace(
        get_historical_candles=AsyncMock(side_effect=historical)
    )
    rpc = SimpleNamespace(
        wait_synchronized=AsyncMock(
            side_effect=TimeoutError("RPC synchronization timed out tinyTok")
        )
    )
    broker = object.__new__(MetaApiBroker)
    broker.account_id = "account-fixture"
    broker.account_instance = account
    broker.api = SimpleNamespace(
        metatrader_account_api=SimpleNamespace(get_account=AsyncMock(return_value=account))
    )
    broker.rpc = rpc
    broker.streaming = SimpleNamespace(connected=True)
    broker.lock = asyncio.Lock()
    broker.account_lock = asyncio.Lock()
    broker.stream_lock = asyncio.Lock()
    vars(broker)["_log_redactions"] = ("tinyTok", "account-fixture")

    logger = logging.getLogger("lonora.metaapi")
    output = StringIO()
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    original_propagate = logger.propagate
    logger.propagate = False
    try:
        try:
            await broker.prepare()
        except LonoraError as error:
            assert error.code == "broker_connection_timeout" and isinstance(
                error.__cause__, TimeoutError
            )
        else:
            raise AssertionError("Scripted RPC synchronization must fail")
        await broker.lock.acquire()
        try:
            bars = await asyncio.wait_for(broker.candles("XAUUSD.a", "4h", 5000), timeout=1)
        finally:
            broker.lock.release()
        assert bars[0].symbol == "XAUUSD.a" and bars[0].timeframe == "4h"
        assert calls[-1] == ("account-fixture", "london", "XAUUSD.a", "4h", None, 1000)
        rpc.wait_synchronized.assert_awaited_once()
        print(
            "PASS native SDK historical REST uses account region/signature and succeeds with a live stream despite failed/locked RPC"
        )

        combinations = [
            (symbol, timeframe)
            for symbol in ("EURUSD.a", "XAUUSD.a", "US30.cash", "BTCUSDm")
            for timeframe in sorted(TIMEFRAMES)
        ]
        results = await asyncio.gather(
            *(broker.candles(symbol, timeframe, 500) for symbol, timeframe in combinations)
        )
        assert all(
            result[0].symbol == symbol and result[0].timeframe == timeframe
            for result, (symbol, timeframe) in zip(results, combinations, strict=True)
        )
        assert len(TIMEFRAMES) == 21 and all(call[1] == "london" for call in calls)
        print(
            "PASS 84 concurrent exact-symbol/timeframe combinations keep broker suffixes and canonical monthly timeframe"
        )

        mixed = await asyncio.gather(
            broker.candles("UNKNOWN.a", "1h", 500),
            broker.candles("EURUSD.a", "1h", 500),
            broker.candles("US30.cash", "1h", 500),
            return_exceptions=True,
        )
        assert isinstance(mixed[0], LonoraError) and mixed[0].code == "symbol_not_found"
        assert isinstance(mixed[1], list) and isinstance(mixed[2], list)
        assert await broker.candles("EMPTY.a", "1h", 500) == []
        print(
            "PASS authoritative unknown-symbol error affects only that request; empty history is not mislabeled an unknown symbol"
        )

        async def fails(expected: str) -> LonoraError:
            try:
                await broker.candles("XAUUSD.a", "1h", 500)
            except LonoraError as error:
                assert error.code == expected, (error.code, expected)
                assert error.__cause__ is not None and error.diagnostic_type
                return error
            raise AssertionError("Expected " + expected)

        mode = "timeout"
        failure = await fails("broker_candles_timeout")
        nested = LonoraError("chart_refresh_failed")
        nested.__cause__ = failure
        assert "Historical REST timed out" in safe_exception_message(nested)
        assert "tinyTok" not in safe_exception_message(nested)
        mode = "credentials"
        await fails("broker_credentials_rejected")
        mode = "account_deleted"
        await fails("broker_account_not_found")
        mode = "generic_404"
        await fails("broker_candles_not_found")
        mode = "invalid_ohlc"
        await fails("broker_candles_invalid")
        captured = output.getvalue()
        assert (
            "TimeoutError" in captured
            and "broker_candles_timeout" in captured
            and "timed out" in captured
        )
        assert all(
            value not in captured
            for value in ("tinyTok", "dXNlcjpwdw==", "https://", "user:pass", "account-fixture")
        )
        print(
            "PASS historical failures preserve causes/codes and meaningful nested diagnostics redact known short secrets, URLs and Basic credentials"
        )

        broker.account_instance = None
        broker.api.metatrader_account_api.get_account.side_effect = errors.NotFoundException(
            "Account not found"
        )
        before = len(calls)
        await fails("broker_account_not_found")
        assert len(calls) == before
        print(
            "PASS failed account lookup is not mislabeled a symbol failure and never reaches history or RPC"
        )
    finally:
        logger.removeHandler(handler)
        logger.propagate = original_propagate


if __name__ == "__main__":
    asyncio.run(main())
