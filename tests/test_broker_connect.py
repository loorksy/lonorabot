"""Connecting a trading account from chat (VISION.md 9.2, section 16 step 1).

The owner names the account in chat; the agent calls broker_connect; the server shows a
broker-destination Secret card for the password (and the MetaApi token once); the gateway
provisions and deploys through MetaApi and wakes the agent with the balance. Runs on the
fake terminal and the fake provisioning API: no network, no real account.
"""

import logging
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from test_supervision import call, database, owner_says, refused, wake  # noqa: E402

from scripts.agent_eval.broker import (  # noqa: E402
    FakeMetaApiBroker,
    FakeMetaApiProvisioning,
    FakeProvisioningApi,
    FakeTerminal,
    installed,
)

SERVER = "Fixture-MT5Trial"
TOKEN = "fixture.metaapi." + uuid4().hex
PASSWORD = "fixture-master-" + uuid4().hex


class World:
    """One owner conversation, a fake MetaApi for one token, and the gateway step."""

    def __init__(self, fixture: Any, api: FakeProvisioningApi):
        self.fixture, self.api = fixture, api

    async def gateway(self, passes: int = 4) -> None:
        from lonora_adapters.storage.broker_secrets import BrokerSecrets
        from lonora_trading.broker_provisioning import maintain_broker_provisioning

        services = self.fixture.gateway()
        secrets = BrokerSecrets(self.fixture.runtime.db, key(self.fixture), self.fixture.owner)

        def client(token: str) -> FakeMetaApiProvisioning:
            return FakeMetaApiProvisioning(self.api, token)

        for _ in range(passes):
            for account_id, data in self.api.accounts.items():
                FakeMetaApiBroker.terminals.setdefault(
                    account_id,
                    FakeTerminal(account_id=account_id, login=data["login"], server=data["server"]),
                )
            with patch(
                "lonora_trading.broker_provisioning.provisioning_client",
                client,
            ):
                await maintain_broker_provisioning(
                    self.fixture.runtime.db, services.brokers, secrets, self.fixture.owner
                )

    async def card(self, card_id: str) -> Any:
        from lonora_db.schema import OwnerActionRow

        async with self.fixture.runtime.db.sessions() as session:
            row = await session.get(OwnerActionRow, card_id)
            assert row is not None
            return row

    async def save(self, card_id: str, values: dict[str, str]) -> Any:
        return await self.fixture.client.post(
            f"/api/owner-actions/{card_id}/secret", json={"values": values}
        )

    async def wake_prompt(self, card_id: str) -> str | None:
        from lonora_db.schema import RunRow
        from lonora_session.idempotency import stable_id

        async with self.fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, stable_id(card_id, "continue-after-card"))
            return run.prompt if run else None


def key(fixture: Any) -> str:
    return fixture.runtime.settings.encryption_key.get_secret_value()


def login() -> str:
    return str(70000000 + int(uuid4().int % 9999999))


async def connect(fixture: Any, agent: dict[str, Any], account: str, server: str = SERVER):
    thread = await fixture.conversation(agent)
    context = await owner_says(
        fixture, agent, thread, "I have an MT5 account at my broker, trade it"
    )
    return await call(context, "broker_connect", login=account, server=server)


async def remove_token(fixture: Any) -> None:
    """Each test starts with no saved MetaApi token (the tests share a database)."""
    from lonora_db.schema import BrokerSessionRow, SecretRow
    from lonora_db.secrets import METAAPI_TOKEN
    from sqlalchemy import delete, select

    async with fixture.runtime.db.sessions() as session, session.begin():
        token = await session.scalar(
            select(SecretRow.id).where(SecretRow.scope == "broker", SecretRow.name == METAAPI_TOKEN)
        )
        if token:
            for row in await session.scalars(select(BrokerSessionRow)):
                if row.payload.get("secret_id") == token:
                    await session.delete(row)
            await session.execute(delete(SecretRow).where(SecretRow.id == token))
        # Cards earlier tests left in flight would be advanced by this test's gateway.
        from lonora_db.schema import OwnerActionRow

        for card in await session.scalars(
            select(OwnerActionRow).where(OwnerActionRow.kind == "secret")
        ):
            if card.result.get("provisioning") in {"pending", "deploying", "reading"}:
                card.result = {**card.result, "provisioning": "failed", "code": "test_cleanup"}


@pytest.mark.asyncio
async def test_the_owner_connects_an_account_from_chat_and_hears_its_balance(
    caplog: pytest.LogCaptureFixture,
) -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.schema import BrokerSessionRow

    caplog.set_level(logging.DEBUG)
    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Connect")
        with installed():
            shown = await connect(fixture, agent, account)
            card_id = shown["owner_action"]["id"]
            assert shown["owner_action"]["kind"] == "secret" and shown["owner_must_tap"]
            assert shown["asks_for"] == ["PASSWORD", "METAAPI_TOKEN"]
            thread_id = (await world.card(card_id)).thread_id
            listed: Any = await fixture.request("GET", "/owner-actions?thread_id=" + thread_id)
            card = next(item for item in listed if item["id"] == card_id)
            assert card["facts"]["secret"]["destination"] == "broker"
            assert card["facts"]["secret"]["account"] == {
                "login": account,
                "server": SERVER,
                "platform": "mt5",
            }
            # A missing field is refused; nothing is stored.
            assert (await world.save(card_id, {"PASSWORD": PASSWORD})).status_code == 422
            saved = await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            assert saved.status_code == 200
            row = await world.card(card_id)
            assert row.status == "confirmed" and row.result["provisioning"] == "pending"
            assert await world.wake_prompt(card_id) is None  # woken once, at the end
            await world.gateway()
            row = await world.card(card_id)
            assert row.result["provisioning"] == "connected", row.result
            prompt = await world.wake_prompt(card_id)
            assert prompt is not None
            assert f"account {account} on {SERVER} is connected" in prompt
            assert "Balance 10000" in prompt and "trading is allowed" in prompt
            assert api.calls.count("create_account") == 1 and len(api.accounts) == 1
            assert api.creates[0]["name"] == "Lonora " + SERVER

            async with fixture.runtime.db.sessions() as session:
                connection = await session.get(BrokerSessionRow, row.result["connection_id"])
                assert connection is not None and connection.payload["enabled"]
                assert connection.payload["account_id"] == next(iter(api.accounts))
                assert connection.state["broker_identity"]["login"] == account
                password_id = connection.state["password_secret_id"]
                token_id = connection.payload["secret_id"]
            broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
            assert await broker.read(password_id) == PASSWORD
            assert await broker.read(token_id) == TOKEN
            # A secret a live connection uses is not deleted (14.3.11, R8).
            for secret_id in (password_id, token_id):
                refused_delete = await fixture.client.delete("/api/secrets/" + secret_id)
                assert refused_delete.status_code == 409

            # A second account asks only for its password: the token is entered once.
            second = login()
            api.servers[SERVER][second] = PASSWORD + "-2"
            again = await connect(fixture, agent, second)
            assert again["asks_for"] == ["PASSWORD"]
            # The same account again is refused before any card or MetaApi call.
            assert await refused_connect(fixture, agent, account) == (
                "broker_account_already_connected"
            )

        await no_value_anywhere(fixture, [PASSWORD, TOKEN], caplog.text)
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


async def no_value_anywhere(fixture: Any, values: list[str], logs: str) -> None:
    """No password or token in any card, event, message or log line."""
    from lonora_db.schema import EventRow, MessageRow, OwnerActionRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        texts = [str(event.payload) for event in await session.scalars(select(EventRow))]
        texts += [message.content for message in await session.scalars(select(MessageRow))]
        texts += [
            str(card.payload) + str(card.result)
            for card in await session.scalars(select(OwnerActionRow))
        ]
    texts.append(logs)
    for text in texts:
        for value in values:
            assert value not in text


async def refused_connect(fixture: Any, agent: dict[str, Any], account: str) -> str:
    thread = await fixture.conversation(agent)
    context = await owner_says(fixture, agent, thread, "connect it again")
    return await refused(context, "broker_connect", login=account, server=SERVER)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "server,password,code",
    [
        (SERVER, "wrong-fixture-password", "broker_password_rejected"),
        ("Unknown-MT5Live", PASSWORD, "broker_server_not_found"),
    ],
)
async def test_a_refused_account_wakes_the_agent_with_the_reason(
    caplog: pytest.LogCaptureFixture, server: str, password: str, code: str
) -> None:
    database()
    caplog.set_level(logging.DEBUG)
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import METAAPI_TOKEN, metaapi_password_name

    fixture = await Fixture().open()
    account = login()
    world = World(fixture, FakeProvisioningApi(servers={SERVER: {account: PASSWORD}}))
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Refused")
        with installed():
            card_id = (await connect(fixture, agent, account, server))["owner_action"]["id"]
            saved = await world.save(card_id, {"PASSWORD": password, "METAAPI_TOKEN": TOKEN})
            assert saved.status_code == 200
            await world.gateway(2)
        row = await world.card(card_id)
        assert row.result["provisioning"] == "failed" and row.result["code"] == code
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and code in prompt and password not in prompt
        assert world.api.accounts == {}
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        # The refused password is forgotten; the token is kept for the next card.
        assert await broker.named(metaapi_password_name(card_id)) is None
        assert await broker.named(METAAPI_TOKEN) is not None
        await no_value_anywhere(fixture, [password, TOKEN], caplog.text)
    finally:
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


@pytest.mark.asyncio
async def test_a_crash_between_create_and_record_never_makes_a_second_account() -> None:
    database()
    from check_streaming import Fixture
    from lonora_trading import broker_provisioning

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    original = broker_provisioning._record  # pyright: ignore[reportPrivateUsage]
    crashed: list[bool] = []

    async def crash_once(session: Any, row: Any, **changes: Any) -> None:
        if changes.get("provisioning") == "deploying" and not crashed:
            crashed.append(True)
            raise RuntimeError("process ended after MetaApi created the account")
        await original(session, row, **changes)

    try:
        await remove_token(fixture)
        agent = await fixture.agent("Crash")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            with patch.object(broker_provisioning, "_record", crash_once):
                await world.gateway(1)
            assert crashed and len(api.accounts) == 1
            assert (await world.card(card_id)).result["provisioning"] == "pending"
            await world.gateway()
        row = await world.card(card_id)
        assert row.result["provisioning"] == "connected", row.result
        # Found again, not created twice, and still known as Lonora's own (R-SEC M1 on
        # #179): a later failure or disconnect removes it.
        assert row.result["created"] is True and row.result["create_sent"] is True
        assert api.calls.count("create_account") == 1 and len(api.accounts) == 1
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


@pytest.mark.asyncio
async def test_only_the_owners_own_message_raises_a_password_card() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Not asked")
        thread = await fixture.conversation(agent)
        routine = await wake(fixture, agent, thread)
        assert await refused(routine, "broker_connect", login=login(), server=SERVER) == (
            "broker_connect_needs_owner_message"
        )
        asked = await owner_says(fixture, agent, thread, "connect my account")
        assert await refused(asked, "broker_connect", login=login(), server="Fixture-Live") == (
            "broker_platform_required"
        )
    finally:
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


def test_the_platform_comes_from_the_server_name() -> None:
    from lonora_trading.broker_provisioning import platform_of

    assert platform_of("Exness-MT5Trial16") == "mt5"
    assert platform_of("ICMarketsSC-MT4-Demo") == "mt4"
    assert platform_of("Broker-mt 5 live") == "mt5"
    assert platform_of("Exness-Real7") is None


@pytest.mark.asyncio
async def test_a_run_that_read_third_party_text_cannot_raise_a_password_card() -> None:
    database()
    from check_streaming import Fixture
    from lonora_tools.provenance import mark_external_content

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Tainted")
        thread = await fixture.conversation(agent)
        context = await owner_says(fixture, agent, thread, "read this page and connect")
        async with fixture.runtime.db.sessions() as session, session.begin():
            await mark_external_content(session, context.lease.run_id, "web_fetch")
        assert await refused(context, "broker_connect", login=login(), server=SERVER) == (
            "broker_connect_needs_owner_message"
        )
    finally:
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


@pytest.mark.asyncio
async def test_a_card_raised_before_the_token_was_saved_never_replaces_it() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import METAAPI_TOKEN

    fixture = await Fixture().open()
    first, second = login(), login()
    world = World(
        fixture, FakeProvisioningApi(servers={SERVER: {first: PASSWORD, second: PASSWORD}})
    )
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Two cards")
        with installed():
            one = (await connect(fixture, agent, first))["owner_action"]["id"]
            two = await connect(fixture, agent, second)
            assert two["asks_for"] == ["PASSWORD", "METAAPI_TOKEN"]  # none saved yet
            await world.save(one, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            saved = await world.save(
                two["owner_action"]["id"],
                {"PASSWORD": PASSWORD, "METAAPI_TOKEN": "fixture.other.token"},
            )
            assert saved.status_code == 200
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        token_id = await broker.named(METAAPI_TOKEN)
        assert token_id is not None and await broker.read(token_id) == TOKEN
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


@pytest.mark.asyncio
async def test_a_transient_metaapi_failure_is_retried_not_ended() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import metaapi_password_name

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(
        servers={SERVER: {account: PASSWORD}}, lose_create_answer="before_commit"
    )
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Transient")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "pending"
            broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
            assert await broker.named(metaapi_password_name(card_id)) is not None
            await world.gateway()
        assert (await world.card(card_id)).result["provisioning"] == "connected"
        # Cards other tests left in this database are advanced too; count this account's.
        assert [create["login"] for create in api.creates].count(account) == 2
        assert [data["login"] for data in api.accounts.values()].count(account) == 1
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)  # later tests expect the accounts they made
        await fixture.close()


@pytest.mark.asyncio
async def test_the_journal_is_never_blocked_while_metaapi_creates_an_account() -> None:
    """R-SEC H1: provisioning holds no owner-row lock across MetaApi's create, so an
    insert that references the owner (a journal reservation) never waits on it."""
    database()
    from check_streaming import Fixture
    from sqlalchemy import text

    fixture = await Fixture().open()
    account = login()
    world = World(fixture, FakeProvisioningApi(servers={SERVER: {account: PASSWORD}}))
    original = FakeMetaApiProvisioning.find_or_create
    probes: list[bool] = []

    async def slow_create(self: Any, **arguments: Any) -> Any:
        # What the door's journal insert takes on the owner row (a foreign key).
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(text("SET LOCAL lock_timeout = '1s'"))
            await session.execute(
                text("SELECT id FROM ln_owners WHERE id = :owner FOR KEY SHARE"),
                {"owner": fixture.owner},
            )
        probes.append(True)
        return await original(self, **arguments)

    try:
        await remove_token(fixture)
        agent = await fixture.agent("Journal")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            with patch.object(FakeMetaApiProvisioning, "find_or_create", slow_create):
                await world.gateway(1)
        assert probes == [True]
        assert (await world.card(card_id)).result["provisioning"] == "deploying"
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_refused_token_on_a_first_account_is_forgotten_and_asked_again() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.secrets import METAAPI_TOKEN

    fixture = await Fixture().open()
    account = login()
    world = World(fixture, FakeProvisioningApi(servers={SERVER: {account: PASSWORD}}))
    world.api.token_valid = False
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Token refused")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(2)
        result = (await world.card(card_id)).result
        assert result["code"] == "broker_token_rejected" and result["token_kept"] is False
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and "call broker_connect again" in prompt
        broker = BrokerSecrets(fixture.runtime.db, key(fixture), fixture.owner)
        assert await broker.named(METAAPI_TOKEN) is None
    finally:
        await remove_token(fixture)
        await fixture.close()


async def backdate(world: World, card_id: str, *fields: str) -> None:
    """Moves the card's timestamps into the past, as if the time limits passed."""
    from lonora_db.schema import OwnerActionRow

    async with world.fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(OwnerActionRow, card_id)
        assert row is not None
        row.result = {**row.result, **dict.fromkeys(fields, "2000-01-01T00:00:00+00:00")}


async def connection_of(world: World, metaapi_id: str) -> dict[str, Any]:
    from lonora_db.schema import BrokerSessionRow
    from sqlalchemy import select

    async with world.fixture.runtime.db.sessions() as session:
        for row in await session.scalars(select(BrokerSessionRow)):
            if row.payload.get("account_id") == metaapi_id:
                return row.state
    raise AssertionError("no connection for this MetaApi account")


async def refused_after_create(world: World, card_id: str, account: str) -> dict[str, Any]:
    """The card created a MetaApi account, then the broker refuses its login past the
    limit, and MetaApi is busy when Lonora removes the account."""
    await world.gateway(1)
    created = (await world.card(card_id)).result
    assert created["provisioning"] == "deploying" and created["created"] is True
    world.api.servers[SERVER][account] = "changed-at-the-broker"
    world.api.remove_fails = 1
    await backdate(world, card_id, "started_at")
    await world.gateway(1)
    failed = (await world.card(card_id)).result
    assert failed["provisioning"] == "failed" and failed["code"] == "broker_login_rejected"
    assert failed["metaapi_cleanup"] == "pending"
    assert created["metaapi_account_id"] in world.api.accounts
    return created


@pytest.mark.asyncio
async def test_an_account_lonora_created_is_removed_later_when_the_first_removal_failed() -> None:
    """R-SEC L1 on #141: a MetaApi account Lonora created for a card that then failed is
    not left billing at MetaApi when its removal fails; the gateway retries it."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Cleanup")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            created = await refused_after_create(world, card_id, account)
            await world.gateway(1)  # the removal is due at once; MetaApi refuses it
            assert api.calls.count("remove") == 1
            await world.gateway(1)  # not due again yet: MetaApi is not asked every pass
            assert api.calls.count("remove") == 1
            assert created["metaapi_account_id"] in api.accounts
            await backdate(world, card_id, "cleanup_at")
            await world.gateway(1)
        assert created["metaapi_account_id"] not in api.accounts
        assert (await world.card(card_id)).result["metaapi_cleanup"] == "removed"
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_leftover_account_another_connection_reused_is_never_removed() -> None:
    """Before the retry removes it, the leftover account was found again by the next
    connect of the same login and server: it is the owner's live account now, still
    known as one Lonora created."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Reused")
        with installed():
            first = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(first, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            metaapi_id = (await refused_after_create(world, first, account))["metaapi_account_id"]
            await world.gateway(1)  # the first retry: MetaApi refuses it again
            removals = api.calls.count("remove")
            # The owner connects again with the password the broker now takes.
            second = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(second, {"PASSWORD": "changed-at-the-broker"})
            await world.gateway()
            again = (await world.card(second)).result
            assert again["provisioning"] == "connected"
            # Lonora created it, so this card owns it as such (R-SEC L1 on #179): a later
            # disconnect removes it.
            assert again["metaapi_account_id"] == metaapi_id and again["lonora_owned"] is True
            assert (await world.card(first)).result["metaapi_cleanup"] == "handed_over"
            await backdate(world, first, "cleanup_at")
            await world.gateway(1)
        assert metaapi_id in api.accounts and api.calls.count("remove") == removals
        assert (await connection_of(world, metaapi_id))["provisioned_by_lonora"] is True
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_leftover_account_a_new_connect_takes_over_is_removed_when_it_fails() -> None:
    """A new connect that finds the leftover account takes over its cleanup (R-SEC L1 on
    #179); when that card fails too, the account is removed, not kept billing."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Waits")
        with installed():
            first = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(first, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            metaapi_id = (await refused_after_create(world, first, account))["metaapi_account_id"]
            second = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(second, {"PASSWORD": "still-wrong"})
            await world.gateway(1)
            again = (await world.card(second)).result
            assert again["provisioning"] == "deploying" and again["lonora_owned"] is True
            assert again["metaapi_account_id"] == metaapi_id
            assert (await world.card(first)).result["metaapi_cleanup"] == "handed_over"
            await backdate(world, second, "started_at")
            await world.gateway(1)
            refused = (await world.card(second)).result
            assert refused["provisioning"] == "failed" and refused["lonora_owned"] is True
            assert metaapi_id in api.accounts  # the removal is the next pass's
            await world.gateway(1)
        assert metaapi_id not in api.accounts
        assert (await world.card(second)).result["metaapi_cleanup"] == "removed"
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "moved,code,observed",
    [
        # Exness moved the demo account to another server: MetaApi says DISCONNECTED.
        (True, "broker_login_not_established", "DISCONNECTED"),
        (False, "broker_login_rejected", "DISCONNECTED_FROM_BROKER"),
    ],
)
async def test_a_deployed_terminal_not_logged_in_fails_with_what_lonora_saw(
    moved: bool, code: str, observed: str
) -> None:
    """The login wait starts when MetaApi first reports the terminal deployed; past
    LOGIN_DEADLINE the card fails with a code for what MetaApi reported, and the wake
    says the usual causes and the fix, never a connection."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Not logged in")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "deploying"
            if moved:
                api.servers[SERVER].pop(account)
                api.servers["Fixture-MT5Trial2"] = {account: PASSWORD}
            else:
                api.servers[SERVER][account] = "changed-at-the-broker"
            await world.gateway(1)
            waiting = (await world.card(card_id)).result
            # Deployed, not logged in yet: the wait starts now, the card is not failed.
            assert waiting["provisioning"] == "deploying" and waiting["deployed_at"]
            metaapi_id = waiting["metaapi_account_id"]
            assert api.accounts[metaapi_id]["connectionStatus"] == observed
            await backdate(world, card_id, "deployed_at")  # only the login wait passed
            await world.gateway(1)
        failed = (await world.card(card_id)).result
        assert failed["provisioning"] == "failed" and failed["code"] == code, failed
        assert failed["started_at"] != "2000-01-01T00:00:00+00:00"
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and code in prompt and observed in prompt
        assert "exactly as his MT5 app shows it now" in prompt and "rotate_password" in prompt
        # An investor password connects read-only: it is never named as a login cause.
        assert "investor" not in prompt
        assert "connected" not in prompt.replace("DISCONNECTED", "")
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_terminal_first_seen_deployed_at_the_deadline_names_no_login_cause() -> None:
    """The whole wait ends just as MetaApi first reports the terminal deployed and not
    logged in: the login wait has not run, so the card fails as a timeout, with no cause
    for a login nobody waited for."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Late deploy")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "deploying"
            api.servers[SERVER].pop(account)  # DISCONNECTED once deployed, no reason given
            await backdate(world, card_id, "started_at")
            await world.gateway(1)
        failed = (await world.card(card_id)).result
        assert failed["provisioning"] == "failed", failed
        assert failed["code"] == "broker_connect_timeout" and failed["deployed_at"]
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and "MT5 app" not in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


def linked_not_logged_in(api: FakeProvisioningApi, account: str) -> str:
    """The owner's token already has a MetaApi account for this login and server, deployed
    with an earlier password the broker refuses: a connect takes the reuse path."""
    metaapi_id = api.link(account, SERVER)
    api.accounts[metaapi_id]["terminal_password"] = "fixture-earlier-password"
    return metaapi_id


@pytest.mark.asyncio
async def test_a_redeploy_refused_while_metaapi_is_busy_is_repeated_not_failed() -> None:
    """Production, 2026-11-19: the reused account gets the new password, and MetaApi then
    refuses the redeploy because it is still deploying the account. The card waits; the
    next pass stores the same saved password again and redeploys, and only that accepted
    redeploy records ``password_set``."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    metaapi_id = linked_not_logged_in(api, account)
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Busy")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            assert (await world.card(card_id)).result["metaapi_account_id"] == metaapi_id
            api.busy = 1
            await world.gateway(1)
            waiting = (await world.card(card_id)).result
            assert waiting["provisioning"] == "deploying", waiting
            assert waiting["password_stored"] is True and "password_set" not in waiting
            assert api.calls.count("update") == 1 and api.calls.count("redeploy") == 1
            assert api.accounts[metaapi_id]["password"] == PASSWORD
            assert api.accounts[metaapi_id]["terminal_password"] == "fixture-earlier-password"
            await world.gateway(1)
            again = (await world.card(card_id)).result
            assert again["provisioning"] == "reading" and again["password_set"] is True, again
            # The same saved password again, then the redeploy MetaApi now takes.
            assert api.calls.count("update") == 2 and api.calls.count("redeploy") == 2
            assert api.accounts[metaapi_id]["terminal_password"] == PASSWORD
            await world.gateway(1)
        assert (await world.card(card_id)).result["provisioning"] == "connected"
        assert len(api.accounts) == 1 and api.creates == []
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_stored_password_is_redeployed_even_once_the_old_terminal_logs_in() -> None:
    """MetaApi stores this card's password, then refuses the redeploy as busy; meanwhile
    the terminal logs in with the password it was deployed with, which MetaApi no longer
    stores. The next pass still redeploys with the stored one, so the broker's answer to
    the password the owner typed decides the card, not a terminal left on another."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    metaapi_id = linked_not_logged_in(api, account)
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Busy then logged in")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            api.busy = 1
            await world.gateway(1)
            assert (await world.card(card_id)).result["password_stored"] is True
            api.servers[SERVER][account] = "fixture-earlier-password"  # it logs in now
            await world.gateway(1)
            assert api.calls.count("update") == 2 and api.calls.count("redeploy") == 2
            assert api.accounts[metaapi_id]["terminal_password"] == PASSWORD
        result = (await world.card(card_id)).result
        assert result["provisioning"] == "deploying" and result["password_set"] is True
        assert api.accounts[metaapi_id]["connectionStatus"] == "DISCONNECTED_FROM_BROKER"
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("busy_state", ["DEPLOYING", "UNDEPLOYING"])
async def test_a_terminal_metaapi_is_still_deploying_is_waited_for(busy_state: str) -> None:
    """While MetaApi reads the account as still deploying or undeploying, a pass neither
    stores the password nor deploys (MetaApi would refuse it); once it settles, the card
    goes on."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    metaapi_id = linked_not_logged_in(api, account)
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Still deploying")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            api.accounts[metaapi_id]["state"] = busy_state
            api.held.add(metaapi_id)
            before = len(api.calls)
            await world.gateway(2)
            waiting = (await world.card(card_id)).result
            assert waiting["provisioning"] == "deploying" and "password_stored" not in waiting
            assert not {"update", "deploy", "redeploy", "undeploy"} & set(api.calls[before:])
            api.held.discard(metaapi_id)
            await world.gateway(2)
        assert (await world.card(card_id)).result["provisioning"] == "connected"
        assert api.accounts[metaapi_id]["terminal_password"] == PASSWORD
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("refused", [True, False])
async def test_an_account_metaapi_is_still_busy_with_at_the_deadline_fails_as_busy(
    refused: bool,
) -> None:
    """MetaApi refuses every redeploy as busy, or reads the account as still deploying,
    until the whole wait ends: the card fails as broker_provisioning_busy, not as a
    rejection and not as a login the broker judged."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    metaapi_id = linked_not_logged_in(api, account)
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Busy at the deadline")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(1)
            if refused:
                api.busy = 100
            else:
                api.accounts[metaapi_id]["state"] = "DEPLOYING"
                api.held.add(metaapi_id)
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "deploying"
            await backdate(world, card_id, "started_at")
            await world.gateway(1)
        failed = (await world.card(card_id)).result
        assert failed["provisioning"] == "failed", failed
        assert failed["code"] == "broker_provisioning_busy"
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None and "broker_provisioning_busy" in prompt
        assert metaapi_id in api.accounts  # the owner's own account is never removed
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_connection_whose_first_read_never_answers_is_linked_not_connected() -> None:
    """MetaApi reported the terminal connected, so the connection is saved, but no read
    answers before READ_DEADLINE: the card says saved and no balance read, and the wake
    says what was seen when, never a login still awaited and never a balance."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Linked")
        with installed():
            card_id = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(card_id, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway(2)
            reading = (await world.card(card_id)).result
            assert reading["provisioning"] == "reading", reading
            terminal = FakeMetaApiBroker.terminals[reading["metaapi_account_id"]]
            terminal.fail("connection_drop", times=100)
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "reading"
            await backdate(world, card_id, "connected_at")
            await world.gateway(1)
        linked = (await world.card(card_id)).result
        assert linked["provisioning"] == "linked" and "account" not in linked, linked
        assert linked["read_code"].startswith("broker_")
        prompt = await world.wake_prompt(card_id)
        assert prompt is not None
        assert "reported its terminal connected to the broker when the connection was saved" in (
            prompt
        )
        assert "no balance was read" in prompt and "MetaApi's stored record" in prompt
        assert "waiting for the broker login" not in prompt
        assert " is connected" not in prompt and "Balance" not in prompt
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reconnect_with_the_server_the_account_moved_to_moves_the_same_account() -> None:
    """The owner names another server for a connected login: the card is for that
    connection, and MetaApi's account gets the new server and password and redeploys.
    No second MetaApi account and no second connection; the old server is not kept."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import BrokerSessionRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    account = login()
    moved_to = "Fixture-MT5Trial2"
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Moved")
        with installed():
            first = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(first, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway()
            connected = (await world.card(first)).result
            assert connected["provisioning"] == "connected", connected
            metaapi_id = connected["metaapi_account_id"]
            # Exness moves the demo account; the old server no longer has the login.
            api.servers[SERVER].pop(account)
            api.servers[moved_to] = {account: PASSWORD + "-main"}
            shown = await connect(fixture, agent, account, server=moved_to)
            assert shown["asks_for"] == ["PASSWORD"] and SERVER in shown["next"]
            card_id = shown["owner_action"]["id"]
            card = await world.card(card_id)
            assert card.payload["purpose"] == "rotate_password"
            assert card.payload["connection_id"] == connected["connection_id"]
            assert card.payload["account"]["server"] == moved_to
            assert card.payload["server_from"] == SERVER
            # The owner sees the move on the card he saves.
            listed: Any = await fixture.request("GET", "/owner-actions?thread_id=" + card.thread_id)
            shown_card = next(item for item in listed if item["id"] == card_id)
            assert shown_card["facts"]["secret"]["server_from"] == SERVER
            assert (await world.save(card_id, {"PASSWORD": PASSWORD + "-main"})).status_code == 200
            await world.gateway(1)
            assert (await world.card(card_id)).result["provisioning"] == "connected"
            assert api.accounts[metaapi_id]["server"] == moved_to
            assert api.accounts[metaapi_id]["connectionStatus"] == "CONNECTED"
            assert [create["login"] for create in api.creates].count(account) == 1
            assert {"redeploy", "update"} <= set(api.calls)
            async with fixture.runtime.db.sessions() as session:
                rows = [
                    row
                    for row in await session.scalars(select(BrokerSessionRow))
                    if account in str(row.state.get("broker_identity"))
                ]
            assert [row.id for row in rows] == [connected["connection_id"]]
            # The connection records the server MetaApi stores now.
            assert rows[0].state["broker_identity"]["server"] == moved_to
            prompt = await world.wake_prompt(card_id)
            assert prompt is not None and f"on server {moved_to} (it had {SERVER})" in prompt
            assert "Whether the broker accepts the login shows only when account_read" in prompt
            # A later plain new password keeps MetaApi on the server it moved to.
            thread = await fixture.conversation(agent)
            context = await owner_says(fixture, agent, thread, "set a new password for it")
            listed = await call(context, "list_accounts")
            mine = [
                item
                for item in listed["accounts"]
                if item["connection_id"] == connected["connection_id"]
            ]
            assert [item["broker_identity"]["server"] for item in mine] == [moved_to]
            again = await call(
                context,
                "broker_manage",
                account_id=connected["connection_id"],
                action="rotate_password",
            )
            plain = await world.card(again["owner_action"]["id"])
            assert plain.payload["account"]["server"] == moved_to
            assert "server_from" not in plain.payload
            assert (await world.save(plain.id, {"PASSWORD": PASSWORD + "-main"})).status_code == 200
            await world.gateway(1)
        assert (await world.card(plain.id)).result["provisioning"] == "connected"
        assert api.accounts[metaapi_id]["server"] == moved_to
        assert api.updates[-1]["server"] == moved_to  # the stored one, sent back unchanged
        rotated = await world.wake_prompt(plain.id)
        assert rotated is not None and "(it had" not in rotated
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_same_login_number_at_another_broker_is_another_account() -> None:
    """A login number is unique only within one broker: the same number on another
    broker's server gets its own connect card, and the saved connection's MetaApi account
    is never touched."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    account = login()
    other = "OtherBroker-MT5Live"
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}, other: {account: "x"}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Two brokers")
        with installed():
            first = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(first, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway()
            connected = (await world.card(first)).result
            assert connected["provisioning"] == "connected", connected
            shown = await connect(fixture, agent, account, server=other)
            card = await world.card(shown["owner_action"]["id"])
        assert card.payload.get("purpose", "connect") == "connect"
        assert "connection_id" not in card.payload and "server_from" not in card.payload
        assert card.payload["account"]["server"] == other
        assert "moves" not in shown["next"]
        assert api.accounts[connected["metaapi_account_id"]]["server"] == SERVER
        assert "update" not in api.calls
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_login_and_server_already_saved_is_refused_even_beside_another_server() -> None:
    """The exact login and server are checked first: with saved connections for the same
    login on two servers, connecting one of them again is refused, never a move of the
    other onto it (two connections for one account)."""
    database()
    from check_streaming import Fixture
    from lonora_db.broker_sessions import BrokerSessionRepository
    from lonora_db.schema import BrokerSessionRow, SecretRow
    from lonora_db.secrets import METAAPI_TOKEN
    from sqlalchemy import select

    fixture = await Fixture().open()
    account = login()
    second = "Fixture-MT5Trial2"
    api = FakeProvisioningApi(servers={SERVER: {account: PASSWORD}})
    world = World(fixture, api)
    try:
        await remove_token(fixture)
        agent = await fixture.agent("Two servers")
        with installed():
            first = (await connect(fixture, agent, account))["owner_action"]["id"]
            await world.save(first, {"PASSWORD": PASSWORD, "METAAPI_TOKEN": TOKEN})
            await world.gateway()
            connected = (await world.card(first)).result
            assert connected["provisioning"] == "connected", connected
            async with fixture.runtime.db.sessions() as session, session.begin():
                token = await session.scalar(
                    select(SecretRow.id).where(
                        SecretRow.scope == "broker", SecretRow.name == METAAPI_TOKEN
                    )
                )
                # A connection saved before moves existed, for the same login elsewhere.
                legacy = await BrokerSessionRepository().create(
                    session,
                    fixture.owner,
                    {
                        "provider": "metaapi",
                        "account_id": api.link(account, second),
                        "secret_id": token,
                        "enabled": True,
                    },
                    broker_identity={"login": account, "server": second, "platform": "mt5"},
                )
            thread = await fixture.conversation(agent)
            context = await owner_says(fixture, agent, thread, "connect my MT5 account")
            code = await refused(context, "broker_connect", login=account, server=second)
        assert code == "broker_account_already_connected"
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(BrokerSessionRow, connected["connection_id"])
            assert row is not None and row.state["broker_identity"]["server"] == SERVER
            assert await session.get(BrokerSessionRow, legacy.id) is not None
    finally:
        FakeMetaApiBroker.terminals.clear()
        await remove_token(fixture)
        await fixture.close()
