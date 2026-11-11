"""An unknown symbol on a connected account is a symbol failure, never a missing account."""

import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from lonora_adapters.brokers.metaapi import MetaApiBroker, provider_error
from lonora_core.user_error import LonoraError

SDK: Any = importlib.import_module("metaapi_cloud_sdk.clients.error_handler")


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Specified symbol not found", "Not found", "Resource missing"])
@pytest.mark.parametrize("read", ["instrument", "quote", "trading_hours"])
async def test_a_symbol_read_on_a_connected_account_reports_the_symbol(
    read: str, message: str
) -> None:
    rpc = SimpleNamespace(
        get_symbol_specification=AsyncMock(side_effect=SDK.NotFoundException(message)),
        get_symbol_price=AsyncMock(side_effect=SDK.NotFoundException(message)),
    )
    broker = object.__new__(MetaApiBroker)
    with patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=rpc)):
        with pytest.raises(LonoraError) as failure:
            await getattr(broker, read)("XAUUSD")
    assert failure.value.code == "symbol_not_found"


def test_a_missing_account_is_still_reported_as_the_account() -> None:
    gone = SDK.NotFoundException("Trading account with id 1f2e not found")
    assert provider_error(gone, "symbol").code == "broker_account_not_found"
    assert provider_error(gone, "account").code == "broker_account_not_found"
    assert provider_error(gone, "rpc").code == "broker_account_not_found"
    both = SDK.NotFoundException("Symbol XAUUSD not found on account 1f2e")
    assert provider_error(both, "symbol").code == "symbol_not_found"
