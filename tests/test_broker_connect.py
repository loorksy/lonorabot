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

        services = self.fixture.runtime.services(self.fixture.owner)
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
        assert row.result["created"] is False  # found again, not created twice
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
