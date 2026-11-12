"""Managing broker connections from chat (VISION.md 9.3; lead decisions Q7-Q10).

Each test connects an account through the connect flow on the fake terminal and fake
MetaApi, then changes it with broker_manage as the owner asked in chat.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from test_broker_connect import (  # noqa: E402
    PASSWORD,
    SERVER,
    TOKEN,
    World,
    connect,
    key,
    login,
    remove_token,
)
from test_supervision import call, database, owner_says, refused, wake  # noqa: E402

from scripts.agent_eval.broker import (  # noqa: E402
    FakeMetaApiBroker,
    FakeMetaApiProvisioning,
    FakeProvisioningApi,
    installed,
)


async def connected(world: World, agent: dict[str, Any], account: str) -> str:
    card_id = (await connect(world.fixture, agent, account))["owner_action"]["id"]
    await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
    await world.gateway()
    result = (await world.card(card_id)).result
    assert result["provisioning"] == "connected", result
    return str(result["connection_id"])


async def asked(fixture: Any, agent: dict[str, Any], text: str) -> Any:
    return await owner_says(fixture, agent, await fixture.conversation(agent), text)


async def row(fixture: Any, connection_id: str) -> Any:
    from lonora_db.schema import BrokerSessionRow

    async with fixture.runtime.db.sessions() as session:
        return await session.get(BrokerSessionRow, connection_id)


def open_world(fixture: Any, *accounts: str) -> World:
    api = FakeProvisioningApi(servers={SERVER: dict.fromkeys(accounts, PASSWORD)})
    services = fixture.runtime.services(fixture.owner)

    def factory(token: str) -> FakeMetaApiProvisioning:
        return FakeMetaApiProvisioning(api, token)

    services.brokers.provisioning_factory = factory
    return World(fixture, api)


@pytest.mark.asyncio
async def test_disable_enable_and_disconnect_from_chat() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import METAAPI_TOKEN

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Manage")
        with installed():
            connection_id = await connected(world, agent, account)
            before = (await row(fixture, connection_id)).version
            context = await asked(fixture, agent, "turn that account off for now")
            off = await call(context, "broker_manage", account_id=connection_id, action="disable")
            assert off["enabled"] is False and "not read or managed" in off["note"]
            stored = await row(fixture, connection_id)
            assert stored.payload["enabled"] is False and stored.version == before + 1
            # The verified identity moves with the version: the account is the same one.
            assert stored.state["broker_identity"]["connection_version"] == stored.version
            on = await call(context, "broker_manage", account_id=connection_id, action="enable")
            assert on["enabled"] is True and (await row(fixture, connection_id)).payload["enabled"]

            password_id = (await row(fixture, connection_id)).state["password_secret_id"]
            gone = await call(
                context, "broker_manage", account_id=connection_id, action="disconnect"
            )
            assert gone["removed_at_metaapi"] is True
        # Lonora created it at MetaApi, so it is removed there; the token is kept.
        assert world.api.accounts == {} and await row(fixture, connection_id) is None
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        assert await broker.named(METAAPI_TOKEN) is not None
        from lonora_db.schema import SecretRow

        async with fixture.runtime.db.sessions() as session:
            assert await session.get(SecretRow, password_id) is None
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_account_the_owner_linked_by_id_stays_at_metaapi_on_disconnect() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        linked = world.api.link(account, SERVER)  # made at metaapi.cloud by the owner
        agent = await fixture.agent("Linked")
        with installed():
            connection_id = await connected(world, agent, account)
            assert (await row(fixture, connection_id)).payload["account_id"] == linked
            context = await asked(fixture, agent, "disconnect it")
            gone = await call(
                context, "broker_manage", account_id=connection_id, action="disconnect"
            )
        assert gone["removed_at_metaapi"] is False and linked in world.api.accounts
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_uncertain_operation_blocks_disable_and_disconnect() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Unsettled")
        with installed():
            connection_id = await connected(world, agent, account)
            context = await asked(fixture, agent, "switch it off")
            with patch(
                "lonora_trading.broker_manage.unsettled_obligation", AsyncMock(return_value=True)
            ):
                for action in ("disable", "disconnect", "rotate_password"):
                    code = await refused(
                        context, "broker_manage", account_id=connection_id, action=action
                    )
                    assert code == "broker_operation_unsettled"
            assert (await row(fixture, connection_id)).payload["enabled"]
            assert world.api.accounts
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_rotating_the_password_goes_through_metaapi_and_moves_the_version() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Rotate")
        with installed():
            connection_id = await connected(world, agent, account)
            before = await row(fixture, connection_id)
            old_password = before.state["password_secret_id"]
            context = await asked(fixture, agent, "I changed my trading password")
            card = await call(
                context, "broker_manage", account_id=connection_id, action="rotate_password"
            )
            assert card["asks_for"] == ["PASSWORD"]
            card_id = card["owner_action"]["id"]
            world.api.servers[SERVER][account] = "fixture-new-password"
            await world.save(card_id, {"PASSWORD": "fixture-new-password"})
            await world.gateway(1)
        assert (await world.card(card_id)).result["provisioning"] == "connected"
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and "new trading password is stored" in prompt
        after = await row(fixture, connection_id)
        assert after.version == before.version + 1
        assert after.state["broker_identity"]["login"] == account
        assert after.state["password_secret_id"] != old_password
        data = next(iter(world.api.accounts.values()))
        assert data["password"] == "fixture-new-password"
        assert data["terminal_password"] == "fixture-new-password"  # redeployed
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        assert await broker.read(after.state["password_secret_id"]) == "fixture-new-password"
        from lonora_db.schema import SecretRow

        async with fixture.runtime.db.sessions() as session:
            assert await session.get(SecretRow, old_password) is None
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_new_token_replaces_the_old_only_when_it_sees_every_account() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import METAAPI_TOKEN

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    other = FakeProvisioningApi()  # another MetaApi user's token: sees none of these
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Token")
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        with installed():
            connection_id = await connected(world, agent, account)
            version = (await row(fixture, connection_id)).version
            for new_token, api, outcome in (
                ("fixture.wrong.token", other, "failed"),
                ("fixture.right.token", world.api, "connected"),
            ):
                context = await asked(fixture, agent, "here is my new MetaApi token")
                card = await call(
                    context, "broker_manage", account_id=connection_id, action="replace_token"
                )
                assert card["asks_for"] == ["METAAPI_TOKEN"]
                card_id = card["owner_action"]["id"]
                await world.save(card_id, {"METAAPI_TOKEN": new_token})
                checked = World(fixture, api)
                await checked.gateway(1)
                result = (await world.card(card_id)).result
                assert result["provisioning"] == outcome, result
                token_id = await broker.named(METAAPI_TOKEN)
                assert token_id is not None
                if outcome == "failed":
                    assert result["code"] == "broker_token_mismatch"
                    assert await broker.read(token_id) == TOKEN  # nothing changed
                    assert (await row(fixture, connection_id)).version == version
        assert await broker.read(token_id) == "fixture.right.token"
        after = await row(fixture, connection_id)
        assert after.payload["secret_id"] == token_id and after.version == version + 1
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_only_the_owners_own_message_changes_a_connection() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Not asked")
        with installed():
            connection_id = await connected(world, agent, account)
            routine = await wake(fixture, agent, await fixture.conversation(agent))
            for action in ("disconnect", "disable", "rotate_password", "replace_token"):
                code = await refused(
                    routine, "broker_manage", account_id=connection_id, action=action
                )
                assert code == "broker_manage_needs_owner_message"
            assert (await row(fixture, connection_id)) is not None
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_disconnect_settles_first_and_removes_at_metaapi_only_after() -> None:
    """Q8: prepare_delete runs first. When it refuses, nothing is removed at MetaApi, so
    broker truth stays for reconciliation."""
    database()
    from check_streaming import Fixture
    from lonora_core.user_error import LonoraError

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Order")
        with installed():
            connection_id = await connected(world, agent, account)
            context = await asked(fixture, agent, "disconnect it")
            refusal = AsyncMock(side_effect=LonoraError("delete_blocked_unresolved_operation", 409))
            with patch("lonora_trading.broker_manage.prepare_delete", refusal):
                code = await refused(
                    context, "broker_manage", account_id=connection_id, action="disconnect"
                )
            assert code == "delete_blocked_unresolved_operation"
            assert world.api.accounts and await row(fixture, connection_id) is not None
            assert "undeploy" not in world.api.calls and "remove" not in world.api.calls
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()
