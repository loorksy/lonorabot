"""MetaApi throttling (the lead's production finding of 2026-11-12).

After many restarts MetaApi answered TooManyRequests, and every synchronization timeout
made the adapter drop its terminal connection and subscribe again within seconds. Now:
MetaApi's recommended retry time is never undercut, a connection that fails to
synchronize is kept (the SDK keeps subscribing it, at MetaApi's times) instead of
replaced by a new subscription, and throttling is reported as ``broker_rate_limited``,
not as a lost link. A connection linked without its region records the region MetaApi
reports.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from lonora_adapters.brokers import metaapi
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.brokers.metaapi_lifecycle import subscribe_locked_until, throttled_until
from lonora_core.user_error import LonoraError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))


def later(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def too_many(seconds: float) -> Exception:
    from metaapi_cloud_sdk.clients.error_handler import TooManyRequestsException

    return TooManyRequestsException(
        "You have used all your account subscriptions quota.",
        {
            "periodInMinutes": 60,
            "requestsPerPeriodAllowed": 10,
            "recommendedRetryTime": later(seconds),
            "type": "LIMIT_ACCOUNT_SUBSCRIPTIONS_PER_USER",
        },
        "https://mt-client-api-v1.london.agiliumtrade.ai/users/current/accounts",
    )


def test_metaapis_retry_time_is_read_from_the_answer_and_from_the_sdks_locks() -> None:
    until = throttled_until(too_many(120))
    assert until is not None and 110 < until - datetime.now(UTC).timestamp() <= 120
    assert throttled_until(TimeoutError()) is None
    websocket = SimpleNamespace(
        _subscribe_lock=None,
        socket_instances={
            "london": {0: [{"subscribeLock": {"recommendedRetryTime": later(300)}}, {}]}
        },
    )
    locked = subscribe_locked_until(websocket)
    assert locked is not None and locked - datetime.now(UTC).timestamp() > 290
    past = SimpleNamespace(_subscribe_lock={"recommendedRetryTime": later(-5)}, socket_instances={})
    assert subscribe_locked_until(past) is None
    assert subscribe_locked_until(None) is None


def account(failure: Exception | None = None) -> Any:
    shared = SimpleNamespace(_closed=False, synchronized=False, is_synchronized=lambda: False)
    connection = SimpleNamespace(
        _closed=False,
        _meta_api_connection=shared,
        connect=AsyncMock(),
        wait_synchronized=AsyncMock(side_effect=failure or TimeoutError()),
        close=AsyncMock(),
    )
    return SimpleNamespace(
        id="fixture-provider-account",
        state="DEPLOYED",
        region="london",
        connection_status="CONNECTED",
        reload=AsyncMock(),
        get_rpc_connection=Mock(return_value=connection),
        get_streaming_connection=Mock(return_value=connection),
    )


def broker(value: Any, websocket: Any = None) -> MetaApiBroker:
    result: Any = MetaApiBroker.__new__(MetaApiBroker)
    result.account_id = "fixture-provider-account"
    result.connection_id = "fixture-owned-connection"
    result.account_instance = value
    result.account_lock = asyncio.Lock()
    result.lock = asyncio.Lock()
    result.stream_lock = asyncio.Lock()
    result.rpc = result.streaming = None
    result._account_resolved_at = 1000.0
    result.api = SimpleNamespace(
        metatrader_account_api=SimpleNamespace(get_account=AsyncMock(return_value=value)),
        _metaapi_websocket_client=websocket,
    )
    return result


@pytest.mark.asyncio
async def test_a_throttled_account_read_waits_metaapis_time_not_thirty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(metaapi, "monotonic", lambda: clock[0])
    adapter = broker(account())
    adapter.account_instance = None
    get = adapter.api.metatrader_account_api.get_account
    get.side_effect = too_many(300)
    with pytest.raises(LonoraError) as first:
        await adapter.resolve_account()
    assert first.value.code == "broker_rate_limited"
    clock[0] += 60  # past the usual 30 s, before MetaApi's time
    with pytest.raises(LonoraError):
        await adapter.resolve_account()
    assert get.await_count == 1  # MetaApi was not asked again early
    clock[0] += 250
    get.side_effect = None
    assert await adapter.resolve_account() is get.return_value


@pytest.mark.asyncio
async def test_a_throttled_subscription_keeps_the_connection_and_says_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metaapi, "monotonic", lambda: 1000.0)
    value = account()
    websocket = SimpleNamespace(
        _subscribe_lock={"recommendedRetryTime": later(600)}, socket_instances={}
    )
    adapter = broker(value, websocket)
    with pytest.raises(LonoraError) as caught:
        await adapter.prepare_stream()
    assert caught.value.code == "broker_rate_limited" and caught.value.status == 429
    connection = value.get_streaming_connection.return_value
    assert adapter.streaming is connection and not connection.close.await_count  # kept
    slot = adapter._slot("streaming")  # pyright: ignore[reportPrivateUsage]
    assert slot.retry_at - asyncio.get_running_loop().time() > 590  # MetaApi's time
    with pytest.raises(LonoraError):
        await adapter.prepare_stream()  # inside the wait: no new subscription
    assert value.get_streaming_connection.call_count == 1
    assert connection.wait_synchronized.await_count == 1
    value.reload.assert_not_awaited()  # throttling is not read as a refused login


@pytest.mark.asyncio
async def test_a_plain_timeout_keeps_the_connection_until_it_is_renewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metaapi, "monotonic", lambda: 1000.0)
    value = account()
    adapter = broker(value)
    connection = value.get_rpc_connection.return_value
    slot = adapter._slot("rpc")  # pyright: ignore[reportPrivateUsage]
    for attempt in range(1, metaapi.KEPT_FAILURES + 1):
        slot.retry_at = 0
        with pytest.raises(LonoraError) as caught:
            await adapter.prepare()
        assert caught.value.code == "broker_connection_timeout"
        assert value.get_rpc_connection.call_count == 1
        assert (adapter.rpc is connection) == (attempt < metaapi.KEPT_FAILURES)


@pytest.mark.asyncio
async def test_a_connection_linked_without_its_region_records_metaapis() -> None:
    from test_supervision import database

    database()
    from check_streaming import Fixture
    from lonora_db.broker_sessions import BrokerSessionRepository
    from lonora_db.schema import BrokerSessionRow

    from scripts.agent_eval.broker import FakeTerminal, installed

    fixture = await Fixture().open()
    terminal = FakeTerminal(account_id="fixture-region-" + str(id(object())), region="london")
    row: Any = None
    try:
        from lonora_adapters.storage.broker_secrets import BrokerSecrets

        secrets = BrokerSecrets(
            fixture.runtime.db,
            fixture.runtime.settings.encryption_key.get_secret_value(),
            fixture.owner,
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            token = await secrets.write_in_session(
                session, "region-" + terminal.account_id, "fixture.token"
            )
            row = await BrokerSessionRepository().create(
                session,
                fixture.owner,
                {
                    "provider": "metaapi",
                    "account_id": terminal.account_id,
                    "secret_id": token,
                    "enabled": True,
                },
                broker_identity={
                    "login": terminal.login + "9",
                    "server": terminal.server,
                    "platform": "mt5",
                },
            )
            version = row.version
        brokers = fixture.runtime.services(fixture.owner).brokers
        with installed(terminal):
            await brokers.account(fixture.owner, row.id)
        async with fixture.runtime.db.sessions() as session:
            saved = await session.get(BrokerSessionRow, row.id)
            assert saved is not None
            assert saved.payload["region"] == "london"
            assert saved.version == version  # not a credential change: no reconnect
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            if row is not None:
                saved = await session.get(BrokerSessionRow, row.id)
                if saved is not None:
                    await session.delete(saved)
        await fixture.close()
