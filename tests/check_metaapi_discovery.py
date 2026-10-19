"""Actual SDK discovery cancellation regressions; scripted HTTP, no broker/network."""

import asyncio
import importlib
import logging
from datetime import datetime
from io import StringIO
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from lonora_adapters.brokers.metaapi import MetaApiBroker, configure_sdk_transport
from lonora_adapters.brokers.metaapi_discovery import update_domain
from lonora_core.user_error import LonoraError

DomainClient: Any = importlib.import_module("metaapi_cloud_sdk.clients.domain_client").DomainClient
SETTINGS = {"domain": "agiliumtrade.ai", "hostname": "mt-client-api-v1"}


async def reproduce_sdk_cancellation() -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def request(*args: Any) -> dict[str, str]:
        entered.set()
        await release.wait()
        return SETTINGS

    client = DomainClient(SimpleNamespace(request=request), "test-token")
    owner = asyncio.create_task(client.get_settings())
    await entered.wait()
    owner.cancel()
    await asyncio.gather(owner, return_exceptions=True)
    promise = client._url_cache["requestPromise"]
    assert promise is not None and not promise.done()
    waiter = asyncio.create_task(client.get_settings())
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert promise.cancelled()
    result = cast(list[Any], await asyncio.gather(client.get_settings(), return_exceptions=True))
    assert isinstance(result[0], asyncio.CancelledError)
    print("PASS actual unpatched SDK reproduces abandoned promise and poisoned cancellation")


async def main() -> None:
    await reproduce_sdk_cancellation()
    configure_sdk_transport()
    assert DomainClient._update_domain is update_domain
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def request(*args: Any) -> dict[str, str]:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return SETTINGS

    client = DomainClient(SimpleNamespace(request=request), "test-token")
    first = asyncio.create_task(client.get_settings())
    await entered.wait()
    others = [asyncio.create_task(client.get_url("https://history", "london")) for _ in range(40)]
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    assert calls == 1 and not client._lonora_domain_slot.task.cancelled()
    release.set()
    results = await asyncio.gather(*others)
    assert all(value == "https://history.london.agiliumtrade.ai" for value in results)
    assert calls == 1 and client._url_cache["requestPromise"] is None
    await client.get_settings()
    assert calls == 1
    client._url_cache["lastUpdated"] = datetime.now().timestamp() - 601
    await asyncio.gather(*(client.get_settings() for _ in range(20)))
    assert calls == 2
    print("PASS cancelling original consumer preserves 40 waiters, one HTTP and ten-minute TTL")

    entered.clear()
    release.clear()
    client._url_cache["lastUpdated"] = 0
    abandoned = [asyncio.create_task(client.get_settings()) for _ in range(12)]
    await entered.wait()
    for task in abandoned:
        task.cancel()
    await asyncio.gather(*abandoned, return_exceptions=True)
    release.set()
    await client._lonora_domain_slot.task
    assert await client.get_settings() == SETTINGS and calls == 3
    print("PASS all consumers may cancel; shared discovery finishes and next request reuses cache")

    for cancelled in (False, True):
        legacy = DomainClient(
            SimpleNamespace(request=AsyncMock(return_value=SETTINGS)), "test-token"
        )
        promise = asyncio.get_running_loop().create_future()
        if cancelled:
            promise.cancel()
        legacy._url_cache["requestPromise"] = promise
        assert await legacy.get_settings() == SETTINGS
        legacy._http_client.request.assert_awaited_once()
        assert legacy._url_cache["requestPromise"] is None
        if not cancelled:
            promise.cancel()
    print("PASS pending or cancelled legacy SDK promises cannot poison fresh discovery")

    async def hung(*args: Any, **kwargs: Any) -> None:
        await asyncio.Event().wait()

    failed = DomainClient(SimpleNamespace(request=AsyncMock(side_effect=hung)), "test-token")
    with patch("lonora_adapters.brokers.metaapi_discovery.DISCOVERY_TIMEOUT_SECONDS", 0.02):
        results = await asyncio.wait_for(
            asyncio.gather(*(failed.get_settings() for _ in range(20)), return_exceptions=True),
            1,
        )
    assert all(
        isinstance(value, LonoraError) and value.code == "broker_connection_timeout"
        for value in results
    )
    assert failed._http_client.request.await_count == 1
    try:
        await failed.get_settings()
    except LonoraError as error:
        assert error.code == "broker_connection_timeout"
    else:
        raise AssertionError("discovery cooldown bypassed")
    assert failed._http_client.request.await_count == 1
    failed._lonora_domain_slot.retry_at = 0
    failed._http_client.request = AsyncMock(return_value=SETTINGS)
    assert await failed.get_settings() == SETTINGS
    assert failed._url_cache["requestPromise"] is None
    print("PASS bounded shared timeout, failure cooldown, clean cache and subsequent recovery")

    cancelled_http = DomainClient(
        SimpleNamespace(request=AsyncMock(side_effect=asyncio.CancelledError)), "test-token"
    )
    try:
        await cancelled_http.get_settings()
    except LonoraError as error:
        assert error.code == "broker_connection_unavailable"
    else:
        raise AssertionError("transport cancellation escaped as consumer cancellation")
    print("PASS independently cancelled transport is a diagnosed broker error, not task death")

    output = StringIO()
    logger = logging.getLogger("lonora.metaapi")
    handler = logging.StreamHandler(output)
    logger.addHandler(handler)
    try:
        rejected = DomainClient(
            SimpleNamespace(
                request=AsyncMock(
                    side_effect=RuntimeError(
                        "Discovery failed token=test-token https://user:pass@host/?token=test-token"
                    )
                )
            ),
            "test-token",
        )
        results = cast(
            list[Any], await asyncio.gather(rejected.get_settings(), return_exceptions=True)
        )
        assert isinstance(results[0], LonoraError)
        assert results[0].code == "broker_connection_unavailable"
        assert "Discovery failed" in output.getvalue()
        assert all(secret not in output.getvalue() for secret in ("test-token", "user:pass"))
    finally:
        logger.removeHandler(handler)
    print("PASS discovery failure preserves useful diagnostics without token or URL credentials")

    original_timeout = asyncio.timeout
    deadlines: list[float] = []

    def short_timeout(seconds: float) -> asyncio.Timeout:
        deadlines.append(seconds)
        return original_timeout(0.02)

    bounded: Any = object.__new__(MetaApiBroker)
    bounded.account_lock = asyncio.Lock()
    bounded.account_instance = None
    bounded.account_id = "fixture-account"
    bounded._log_redactions = ("test-token",)
    bounded.api = SimpleNamespace(
        metatrader_account_api=SimpleNamespace(get_account=AsyncMock(side_effect=hung))
    )
    with patch("lonora_adapters.brokers.metaapi.asyncio.timeout", side_effect=short_timeout):
        result = cast(
            list[Any], await asyncio.gather(bounded.resolve_account(), return_exceptions=True)
        )
        assert isinstance(result[0], LonoraError) and result[0].code == "broker_connection_timeout"
        bounded.account_instance = SimpleNamespace(
            get_historical_candles=AsyncMock(side_effect=hung)
        )
        result = cast(
            list[Any],
            await asyncio.gather(bounded.candles("BTCUSD#", "4h", 500), return_exceptions=True),
        )
        assert isinstance(result[0], LonoraError) and result[0].code == "broker_candles_timeout"
    assert deadlines == [25, 35]
    print("PASS metadata and historical SDK read loops have explicit25s/35s deadlines")

    entered.clear()
    release.clear()
    closing = DomainClient(SimpleNamespace(request=request), "test-token")
    consumer = asyncio.create_task(closing.get_settings())
    await entered.wait()
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)
    broker: Any = object.__new__(MetaApiBroker)
    broker.api = SimpleNamespace(
        _metaapi_websocket_client=SimpleNamespace(_domain_client=closing), close=lambda: None
    )
    broker.rpc = broker.streaming = None
    await broker.close()
    assert closing._lonora_domain_slot.task.cancelled()
    assert closing._url_cache["requestPromise"] is None
    print("PASS broker shutdown explicitly drains shielded discovery owner")


if __name__ == "__main__":
    asyncio.run(main())
