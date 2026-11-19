"""Connecting from chat says "connected" only when the MT5 terminal itself answered
(the lead's production finding of 2026-11-19).

The owner reconnected an Exness demo account from chat. Lonora reused its MetaApi
account, stored the new password and redeployed; the account stayed DEPLOYED but
DISCONNECTED from the broker, yet the owner heard the identity was confirmed, from
MetaApi's stored account record. Now:
- a card ends ``connected`` only after the account read through the synchronized
  terminal succeeds and names the typed login and server;
- the state a redeploy answers is never trusted: the next pass reads MetaApi again, and
  the restarted terminal gets its own time to log in;
- a terminal that never logs in or synchronizes ends ``unconfirmed`` or ``failed`` with
  MetaApi's own word and the fix from chat;
- a reconnect on another server of the same broker moves the MetaApi account there.
Fake terminal and fake MetaApi only: no network, no real account.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from test_broker_connect import (  # noqa: E402
    PASSWORD,
    TOKEN,
    World,
    backdate,
    connect,
    login,
    remove_token,
)
from test_supervision import database  # noqa: E402

from scripts.agent_eval.broker import (  # noqa: E402
    FakeMetaApiBroker,
    FakeProvisioningApi,
    FakeTerminal,
    installed,
)

OLD = "Exness-MT5Trial10"
NEW = "Exness-MT5Trial16"


async def opened() -> Any:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    await remove_token(fixture)
    return fixture


@pytest.mark.asyncio
async def test_a_reused_account_the_broker_refuses_is_never_called_connected() -> None:
    fixture = await opened()
    account = login()
    api = FakeProvisioningApi(servers={NEW: {account: PASSWORD}})
    metaapi_id = api.link(account, NEW)
    # As in production: deployed, but the broker refuses the password MetaApi holds.
    api.accounts[metaapi_id].update(password="stale", terminal_password="stale")
    world = World(fixture, api)
    try:
        agent = await fixture.agent("Refused reconnect")
        with installed():
            card = (await connect(fixture, agent, account, NEW))["owner_action"]["id"]
            await world.save(card, {"PASSWORD": "not-the-password", "METAAPI_TOKEN": TOKEN})
            # Found again (no second account), the typed password stored, redeployed.
            await world.gateway(2)
            row = (await world.card(card)).result
            assert row["provisioning"] == "deploying" and row["metaapi_account_id"] == metaapi_id
            assert api.calls.count("redeploy") == 1 and "create_account" not in api.calls
            assert api.accounts[metaapi_id]["connectionStatus"] == "DISCONNECTED_FROM_BROKER"
            # Within the restarted terminal's login time nothing is concluded.
            await world.gateway(1)
            assert (await world.card(card)).result["provisioning"] == "deploying"
            await backdate(world, card, "restarted_at")
            await world.gateway(1)
        row = (await world.card(card)).result
        assert row["provisioning"] == "failed" and row["code"] == "broker_login_rejected"
        assert "connection_id" not in row
        prompt = await world.wake_prompt(card)
        assert prompt is not None and "DISCONNECTED_FROM_BROKER" in prompt
        assert "rotate_password" in prompt and "server name their MT5 shows" in prompt
        assert "is logged in" not in prompt and "is connected" not in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_terminal_that_never_synchronizes_ends_unconfirmed_not_connected() -> None:
    fixture = await opened()
    account = login()
    api = FakeProvisioningApi(servers={NEW: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        agent = await fixture.agent("Never synchronizes")
        with installed():
            card = (await connect(fixture, agent, account, NEW))["owner_action"]["id"]
            await world.save(card, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(2)
            row = (await world.card(card)).result
            assert row["provisioning"] == "reading", row
            # MetaApi says CONNECTED, but every read through the terminal fails.
            metaapi_id = row["metaapi_account_id"]
            terminal = FakeTerminal(account_id=metaapi_id, login=account, server=NEW)
            terminal.fail("connection_drop", times=1000)
            FakeMetaApiBroker.terminals[metaapi_id] = terminal
            await fixture.gateway().brokers.close()
            fixture._gateway = None
            await world.gateway(1)
            assert (await world.card(card)).result["provisioning"] == "reading"
            assert await world.wake_prompt(card) is None
            await backdate(world, card, "connected_at")
            await world.gateway(1)
        row = (await world.card(card)).result
        assert row["provisioning"] == "unconfirmed"
        assert row["code"] == "broker_terminal_not_synchronized"
        prompt = await world.wake_prompt(card)
        assert prompt is not None and "NOT confirmed at the broker" in prompt
        assert "Never say it is connected or confirmed" in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reconnect_on_another_server_of_the_broker_moves_the_metaapi_account() -> None:
    fixture = await opened()
    account = login()
    # The owner's demo account moved from Trial10 to Trial16; MetaApi still has Trial10.
    api = FakeProvisioningApi(servers={NEW: {account: PASSWORD}, OLD: {}})
    metaapi_id = api.link(account, OLD)
    # The owner's MT5 account itself is on the new server.
    FakeMetaApiBroker.terminals[metaapi_id] = FakeTerminal(
        account_id=metaapi_id, login=account, server=NEW
    )
    world = World(fixture, api)
    try:
        agent = await fixture.agent("Moved server")
        with installed():
            card = (await connect(fixture, agent, account, NEW))["owner_action"]["id"]
            await world.save(card, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(4)
        row = (await world.card(card)).result
        assert row["metaapi_account_id"] == metaapi_id and row["move_server_to"] == NEW
        assert "create_account" not in api.calls and len(api.accounts) == 1
        assert api.updates and api.updates[-1]["server"] == NEW, (api.calls, row)
        assert api.accounts[metaapi_id]["server"] == NEW
        assert row["provisioning"] == "connected", row
        # Named from what the synchronized terminal reported.
        assert row["observed"]["server"] == NEW and row["observed"]["login"] == account
        prompt = await world.wake_prompt(card)
        assert prompt is not None and f"account {account} on {NEW} is logged in" in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_another_brokers_account_with_the_same_login_is_never_moved() -> None:
    fixture = await opened()
    account = login()
    api = FakeProvisioningApi(servers={NEW: {account: PASSWORD}, "Other-Live": {}})
    other = api.link(account, "Other-Live")
    world = World(fixture, api)
    try:
        agent = await fixture.agent("Other broker")
        with installed():
            card = (await connect(fixture, agent, account, NEW))["owner_action"]["id"]
            await world.save(card, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(4)
        row = (await world.card(card)).result
        assert row["metaapi_account_id"] != other and "move_server_to" not in row
        assert api.calls.count("create_account") == 1
        assert api.accounts[other]["server"] == "Other-Live"
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()
