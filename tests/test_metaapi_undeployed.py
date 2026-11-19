"""An account undeployed at MetaApi (the lead's production finding of 2026-11-17).

The account was undeployed on MetaApi's side, and the SDK kept subscribing it about
1,900 times a day, each answered "you have no accounts deployed yet" (400). Now both
terminal connections are dropped, so the SDK stops subscribing; every caller is answered
``broker_account_undeployed`` at once; MetaApi is asked again with one account read only
after ``UNDEPLOYED_RECHECK_SECONDS`` (or right after the owner deploys from chat), and
streaming resumes only once the account reads DEPLOYED.
"""

import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_adapters.brokers import metaapi
from lonora_adapters.brokers.metaapi import UNDEPLOYED_RECHECK_SECONDS, provider_error
from lonora_core.user_error import LonoraError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_metaapi_rate_limits import account, broker  # noqa: E402


def no_accounts_deployed() -> Exception:
    module: Any = importlib.import_module("metaapi_cloud_sdk.clients.error_handler")
    return module.ValidationException(
        "You have no accounts deployed yet. Please deploy an account first", []
    )


def synchronized_stream() -> Any:
    return SimpleNamespace(
        _closed=False,
        _meta_api_connection=SimpleNamespace(
            _closed=False, synchronized=True, is_synchronized=lambda: True
        ),
        connect=AsyncMock(),
        close=AsyncMock(),
    )


async def refused(adapter: Any, kind: str = "rpc") -> str:
    with pytest.raises(LonoraError) as failure:
        await adapter._prepare_connection(kind)
    return failure.value.code


def test_metaapis_no_accounts_deployed_answer_reads_undeployed() -> None:
    assert provider_error(no_accounts_deployed(), "rpc").code == "broker_account_undeployed"
    module: Any = importlib.import_module("metaapi_cloud_sdk.clients.error_handler")
    other = module.ValidationException("Validation failed", [])
    assert provider_error(other, "rpc").code == "broker_request_rejected"


@pytest.mark.asyncio
async def test_an_account_undeployed_at_metaapi_stops_every_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metaapi, "monotonic", lambda: 1000.0)
    value = account()

    async def undeployed() -> None:
        value.state = "UNDEPLOYED"

    value.reload = AsyncMock(side_effect=undeployed)
    adapter: Any = broker(value)
    stream = synchronized_stream()
    adapter.streaming = stream
    rpc = value.get_rpc_connection.return_value
    # The terminal never synchronizes; the fresh account read shows why.
    assert await refused(adapter) == "broker_account_undeployed"
    # Both connections are closed, so the SDK no longer subscribes either.
    assert adapter.rpc is None and adapter.streaming is None
    assert stream.close.await_count == 1 and rpc._closed
    assert UNDEPLOYED_RECHECK_SECONDS == 600

    # Until the re-check, every caller is answered at once: nothing reaches MetaApi.
    get = adapter.api.metatrader_account_api.get_account
    for kind in ("rpc", "streaming"):
        assert await refused(adapter, kind) == "broker_account_undeployed"
    with pytest.raises(LonoraError):
        await adapter.read_rpc("get_symbols")
    with pytest.raises(LonoraError):
        await adapter.resolve_account()
    assert get.await_count == 0 and value.get_rpc_connection.call_count == 1
    assert value.get_streaming_connection.call_count == 0

    # The re-check is due: one account read, still undeployed, and no subscription.
    adapter.undeployed_until = time.time() - 1
    adapter.account_instance = None
    get.return_value = value
    assert await refused(adapter, "streaming") == "broker_account_undeployed"
    assert get.await_count == 1 and value.get_streaming_connection.call_count == 0
    assert adapter.undeployed_until > time.time() + UNDEPLOYED_RECHECK_SECONDS - 5

    # Deployed again: the next re-check reads DEPLOYED and streaming resumes.
    adapter.undeployed_until = time.time() - 1
    adapter.account_instance = None
    value.state = "DEPLOYED"
    value.get_streaming_connection.return_value = synchronized_stream()
    adapter._slot("streaming").ready()
    assert await adapter._prepare_connection("streaming") is not None
    assert value.get_streaming_connection.call_count == 1


@pytest.mark.asyncio
async def test_a_request_answered_no_accounts_deployed_drops_both_connections() -> None:
    value = account()
    adapter: Any = broker(value)
    rpc = synchronized_stream()
    rpc.get_symbols = AsyncMock(side_effect=no_accounts_deployed())
    stream = synchronized_stream()
    adapter.rpc, adapter.streaming = rpc, stream
    with pytest.raises(LonoraError) as failure:
        await adapter.read_rpc("get_symbols")
    assert failure.value.code == "broker_account_undeployed"
    assert adapter.rpc is None and adapter.streaming is None
    assert await refused(adapter) == "broker_account_undeployed"


@pytest.mark.asyncio
async def test_deploying_from_chat_lets_the_adapter_ask_metaapi_at_once() -> None:
    from lonora_trading.broker_manage import recheck_after_deploy

    value = account()
    adapter: Any = broker(value)
    await adapter.stand_down_if_undeployed(LonoraError("broker_account_undeployed", 409))
    assert await refused(adapter) == "broker_account_undeployed"
    recheck_after_deploy(
        SimpleNamespace(connections={"fixture-owned-connection": (1, adapter)}),
        "fixture-owned-connection",
    )
    assert adapter.undeployed_until == 0.0 and adapter.account_instance is None
    get = adapter.api.metatrader_account_api.get_account
    assert await adapter.resolve_account() is value and get.await_count == 1
