"""Provider-stopped accounts never enter terminal synchronization or auto-deploy."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from lonora_adapters.brokers import metaapi
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_core.user_error import LonoraError


def account(state: str) -> Any:
    shared = SimpleNamespace(_closed=False, synchronized=True, is_synchronized=lambda: True)
    connection = SimpleNamespace(
        _closed=False,
        _meta_api_connection=shared,
        connect=AsyncMock(),
        wait_synchronized=AsyncMock(),
    )
    return SimpleNamespace(
        state=state,
        region="fixture-region",
        get_rpc_connection=Mock(return_value=connection),
        get_streaming_connection=Mock(return_value=connection),
        get_historical_candles=AsyncMock(return_value=[]),
        deploy=AsyncMock(),
        redeploy=AsyncMock(),
    )


def broker(value: Any, clock: float = 1000) -> MetaApiBroker:
    result: Any = MetaApiBroker.__new__(MetaApiBroker)
    result.account_id = "fixture-provider-account"
    result.connection_id = "fixture-owned-connection"
    result.account_instance = value
    result.account_lock = asyncio.Lock()
    result.lock = asyncio.Lock()
    result.stream_lock = asyncio.Lock()
    result.rpc = result.streaming = None
    result._account_resolved_at = clock
    result.api = SimpleNamespace(
        metatrader_account_api=SimpleNamespace(get_account=AsyncMock(return_value=value))
    )
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["rpc", "streaming"])
@pytest.mark.parametrize(
    "state,code",
    [
        ("UNDEPLOYED", "broker_account_undeployed"),
        ("UNDEPLOYING", "broker_account_undeployed"),
        ("DEPLOYING", "broker_account_not_ready"),
        ("DEPLOY_FAILED", "broker_account_not_ready"),
        ("DELETING", "broker_account_not_ready"),
        ("REDEPLOY_FAILED", "broker_account_not_ready"),
        ("FUTURE_TERMINAL_STATE", "broker_account_not_ready"),
    ],
)
async def test_inactive_provider_fails_before_connection_and_never_autodeploys(
    monkeypatch: pytest.MonkeyPatch, kind: str, state: str, code: str
) -> None:
    monkeypatch.setattr(metaapi, "monotonic", lambda: 1000.0)
    value = account(state)
    adapter = broker(value)
    for _ in range(3):
        with pytest.raises(LonoraError) as caught:
            await (adapter.prepare() if kind == "rpc" else adapter.prepare_stream())
        assert caught.value.code == code and caught.value.status == 409
    value.get_rpc_connection.assert_not_called()
    value.get_streaming_connection.assert_not_called()
    value.deploy.assert_not_awaited()
    value.redeploy.assert_not_awaited()
    adapter.api.metatrader_account_api.get_account.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["rpc", "streaming"])
async def test_recovery_refreshes_metadata_then_reuses_one_connection(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(metaapi, "monotonic", lambda: clock[0])
    previous = account("UNDEPLOYED")
    adapter = broker(previous)
    with pytest.raises(LonoraError, match="broker_account_undeployed"):
        await (adapter.prepare() if kind == "rpc" else adapter.prepare_stream())
    ready = account("DEPLOYED")
    adapter.api.metatrader_account_api.get_account.return_value = ready
    clock[0] += 31
    getattr(
        adapter, "rpc_slot" if kind == "rpc" else "stream_slot"
    ).retry_at = 0  # Simulate the separate shared-connection backoff elapsing.
    connections = await asyncio.gather(
        *((adapter.prepare() if kind == "rpc" else adapter.prepare_stream()) for _ in range(10))
    )
    assert all(item is connections[0] for item in connections)
    adapter.api.metatrader_account_api.get_account.assert_awaited_once()
    connections[0].connect.assert_awaited_once()
    connections[0].wait_synchronized.assert_not_awaited()
    assert adapter.account_instance is ready
    previous.deploy.assert_not_awaited()
    ready.deploy.assert_not_awaited()


@pytest.mark.asyncio
async def test_metadata_failure_is_shared_and_recovers_without_request_storm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(metaapi, "monotonic", lambda: clock[0])
    adapter = broker(None)
    adapter.api.metatrader_account_api.get_account.side_effect = TimeoutError("fixture failure")
    results = await asyncio.gather(
        *(adapter.resolve_account() for _ in range(10)), return_exceptions=True
    )
    assert all(
        isinstance(item, LonoraError) and item.code == "broker_connection_timeout"
        for item in results
    )
    assert adapter.api.metatrader_account_api.get_account.await_count == 1
    clock[0] += 31
    ready = account("DEPLOYED")
    adapter.api.metatrader_account_api.get_account.side_effect = None
    adapter.api.metatrader_account_api.get_account.return_value = ready
    results = await asyncio.gather(*(adapter.resolve_account() for _ in range(10)))
    assert all(item is ready for item in results)
    assert adapter.api.metatrader_account_api.get_account.await_count == 2


@pytest.mark.asyncio
async def test_history_does_not_acquire_a_terminal_connection_or_require_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metaapi, "monotonic", lambda: 1000.0)
    value = account("UNDEPLOYED")
    adapter = broker(value)
    assert await adapter.candles("unmodified.symbol#", "1m", 10) == []
    value.get_historical_candles.assert_awaited_once_with(
        symbol="unmodified.symbol#", timeframe="1m", start_time=None, limit=10
    )
    value.get_rpc_connection.assert_not_called()
    value.get_streaming_connection.assert_not_called()
    value.deploy.assert_not_awaited()
