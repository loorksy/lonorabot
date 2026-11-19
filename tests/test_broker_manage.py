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
    context = await owner_says(fixture, agent, await fixture.conversation(agent), text)
    # The agent's run, and so its tools, runs in the Gateway (the only MetaApi connections).
    return fixture.gateway().tool_context(
        context.agent_id, context.thread_id, context.lease, fixture.settings.artifact_root
    )


async def row(fixture: Any, connection_id: str) -> Any:
    from lonora_db.schema import BrokerSessionRow

    async with fixture.runtime.db.sessions() as session:
        return await session.get(BrokerSessionRow, connection_id)


def open_world(fixture: Any, *accounts: str) -> World:
    api = FakeProvisioningApi(servers={SERVER: dict.fromkeys(accounts, PASSWORD)})
    services = fixture.gateway()

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
            assert "no longer read or managed" in gone["note"] and gone["open_positions"] == 0
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
@pytest.mark.parametrize("settles", [True, False])
async def test_a_new_password_metaapi_cannot_redeploy_yet_still_reaches_the_terminal(
    settles: bool,
) -> None:
    """MetaApi stores the new password, then refuses the redeploy because it is still
    deploying the account (production, 2026-11-19). The card waits instead of ending:
    the next pass only redeploys, and the password reaches the terminal. Still busy at
    the deadline, the wake says the password is stored and recorded, that no redeploy
    was confirmed and why, and how to redeploy it: never that a deploy comes by itself."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import SecretRow
    from test_broker_connect import backdate

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Rotate busy")
        with installed():
            connection_id = await connected(world, agent, account)
            before = await row(fixture, connection_id)
            old_password = before.state["password_secret_id"]
            context = await asked(fixture, agent, "I changed my trading password")
            card = await call(
                context, "broker_manage", account_id=connection_id, action="rotate_password"
            )
            card_id = card["owner_action"]["id"]
            world.api.servers[SERVER][account] = "fixture-new-password"
            world.api.busy = 3 if settles else 100
            await world.save(card_id, {"PASSWORD": "fixture-new-password"})
            await world.gateway(1)
            waiting = (await world.card(card_id)).result
            assert waiting["provisioning"] == "pending" and waiting["password_stored"], waiting
            assert await world.wake_prompt(card_id) is None  # woken once, at the end
            data = next(iter(world.api.accounts.values()))
            assert data["password"] == "fixture-new-password"
            assert data["terminal_password"] == PASSWORD  # not redeployed yet
            after = await row(fixture, connection_id)
            assert after.version == before.version + 1
            assert after.state["password_secret_id"] != old_password
            async with fixture.runtime.db.sessions() as session:
                assert await session.get(SecretRow, old_password) is None
            await world.gateway(2)
            # Still busy: each pass asks for the redeploy only, never sends the password again.
            assert (await world.card(card_id)).result["provisioning"] == "pending"
            assert world.api.calls.count("update") == 1
            assert world.api.calls.count("redeploy") == 3
            if not settles:
                await backdate(world, card_id, "started_at")
            await world.gateway(1)
        result = (await world.card(card_id)).result
        # The later pass only redeploys: the password is not stored or recorded again.
        assert world.api.calls.count("update") == 1
        assert (await row(fixture, connection_id)).version == after.version
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None
        if settles:
            assert result["provisioning"] == "connected", result
            assert data["terminal_password"] == "fixture-new-password"
            assert "new trading password is stored" in prompt
        else:
            assert result["provisioning"] == "failed", result
            assert result["code"] == "broker_provisioning_busy"
            assert data["terminal_password"] == PASSWORD
            assert "stored at MetaApi and recorded" in prompt
            assert "no redeploy of the terminal with it was confirmed" in prompt
            assert "broker_provisioning_busy" in prompt and "still deploying" in prompt
            assert "call broker_manage rotate_password again" in prompt
            assert "next deploy" not in prompt and "reconnects" not in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("meanwhile", ["rotate_password", "disconnect"])
async def test_a_new_password_replaced_while_its_card_waits_is_never_called_stored(
    meanwhile: str,
) -> None:
    """A new-password card waits while MetaApi refuses its redeploy as busy. Meanwhile a
    second new-password card for the same connection stores its own password (which
    deletes the first card's), or the owner disconnects the account. The first card then
    ends as superseded: its wake never says its password is stored at MetaApi and
    recorded, nor asks the owner to type it again over the newer one."""
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Rotate meanwhile")
        with installed():
            connection_id = await connected(world, agent, account)
            context = await asked(fixture, agent, "I changed my trading password")
            card = await call(
                context, "broker_manage", account_id=connection_id, action="rotate_password"
            )
            first = card["owner_action"]["id"]
            world.api.busy = 100
            await world.save(first, {"PASSWORD": "fixture-first-password"})
            await world.gateway(1)
            assert (await world.card(first)).result["password_stored"] is True
            second = None
            if meanwhile == "rotate_password":
                context = await asked(fixture, agent, "I changed it once more")
                card = await call(
                    context, "broker_manage", account_id=connection_id, action="rotate_password"
                )
                second = card["owner_action"]["id"]
                world.api.servers[SERVER][account] = "fixture-second-password"
                await world.save(second, {"PASSWORD": "fixture-second-password"})
            else:
                context = await asked(fixture, agent, "disconnect it")
                await call(context, "broker_manage", account_id=connection_id, action="disconnect")
            await world.gateway(1)
            world.api.busy = 0
            await world.gateway(1)
        ended = (await world.card(first)).result
        assert ended["provisioning"] == "failed", ended
        assert ended["code"] == "broker_rotation_superseded"
        prompt = await world.wake_prompt(first)
        assert prompt is not None and "broker_rotation_superseded" in prompt
        assert "stored at MetaApi and recorded" not in prompt
        assert "rotate_password again" not in prompt and "same new password" not in prompt
        if second is not None:
            # The newer password is the one MetaApi and the connection hold and run.
            assert (await world.card(second)).result["provisioning"] == "connected"
            data = next(iter(world.api.accounts.values()))
            assert data["password"] == data["terminal_password"] == "fixture-second-password"
            broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
            secret_id = (await row(fixture, connection_id)).state["password_secret_id"]
            assert await broker.read(secret_id) == "fixture-second-password"
        else:
            assert await row(fixture, connection_id) is None
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


@pytest.mark.asyncio
async def test_deploy_restarts_an_undeployed_account_on_the_owners_word() -> None:
    """9.4 and Q13: Lonora proposes the fix, and deploys after the owner's reply."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    world = open_world(fixture, account)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Deploy")
        with installed():
            connection_id = await connected(world, agent, account)
            metaapi_id = (await row(fixture, connection_id)).payload["account_id"]
            running = await call(
                await asked(fixture, agent, "start it"),
                "broker_manage",
                account_id=connection_id,
                action="deploy",
            )
            assert running["state"] == "DEPLOYED" and "nothing was changed" in running["note"]
            assert "deploy" not in world.api.calls
            world.api.accounts[metaapi_id]["state"] = "UNDEPLOYED"  # stopped at MetaApi
            routine = await wake(fixture, agent, await fixture.conversation(agent))
            code = await refused(
                routine, "broker_manage", account_id=connection_id, action="deploy"
            )
            assert code == "broker_manage_needs_owner_message"
            assert "deploy" not in world.api.calls
            context = await asked(fixture, agent, "yes, start it again")
            done = await call(context, "broker_manage", account_id=connection_id, action="deploy")
            assert done["state"] in {"DEPLOYING", "DEPLOYED"}
            assert "recovers by itself" in done["note"]
            assert world.api.accounts[metaapi_id]["state"] == "DEPLOYED"
            context = await asked(fixture, agent, "switch it off, then start it")
            await call(context, "broker_manage", account_id=connection_id, action="disable")
            world.api.accounts[metaapi_id]["state"] = "UNDEPLOYED"
            code = await refused(
                context, "broker_manage", account_id=connection_id, action="deploy"
            )
            assert code == "broker_disabled"  # a switched-off connection is not started
            assert world.api.calls.count("deploy") == 1
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()
