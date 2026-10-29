"""Identity reads use provider metadata and never start a trading/RPC session."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_contracts.broker import BrokerConnection
from lonora_db.broker_sessions import broker_identity_key
from pydantic import ValidationError


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [4, 5])
async def test_actual_metatrader_identity_uses_only_read_only_metadata(version: int):
    broker = object.__new__(MetaApiBroker)
    broker.resolve_account = AsyncMock(
        return_value=SimpleNamespace(
            login=12345, server=" Fixture-Demo ", version=version, name="Owner"
        )
    )
    broker.prepare = AsyncMock(side_effect=AssertionError("RPC must not be started"))
    identity = await broker.metadata_identity()
    assert identity == {
        "login": "12345",
        "server": "Fixture-Demo",
        "broker": None,
        "name": "Owner",
        "platform": f"mt{version}",
    }
    broker.resolve_account.assert_awaited_once_with()
    broker.prepare.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_metadata_does_not_invent_an_identity():
    broker = object.__new__(MetaApiBroker)
    broker.resolve_account = AsyncMock(return_value=SimpleNamespace(version=99))
    identity = await broker.metadata_identity()
    assert broker_identity_key(identity) is None
    assert identity["platform"] is None


def test_user_payload_cannot_supply_its_own_verified_identity():
    with pytest.raises(ValidationError):
        BrokerConnection.model_validate(
            {
                "provider": "metaapi",
                "account_id": "external",
                "broker_identity": {"login": "123", "server": "demo", "platform": "mt5"},
            }
        )
