"""The Secret card (VISION.md 7.2.1-7.2.4, 10.3).

The agent chooses the card's label and fields; the server sets the destination. The
owner's values go straight to the encrypted store in the transaction that settles the
card; the agent learns only which keys were saved, and no value reaches the card, an
event, a message or a run.
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.schema import EventRow, MessageRow, OwnerActionRow, RunRow, SecretRow
from lonora_security.network import endpoint_sha256
from lonora_tools.loader import load_tools
from pydantic import ValidationError
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def test_a_card_subject_fits_whatever_the_keys() -> None:
    from lonora_db.secret_cards import secret_card_payload

    keys = ["COINBASE_ADVANCED_TRADE_API_KEY_" + str(i) + "_" + "X" * 30 for i in range(8)]
    subject, _ = secret_card_payload(
        OwnerActionProposal.model_validate(
            {
                "kind": "secret",
                "label": "Coinbase",
                "secret_fields": [{"key": key, "label": "k"} for key in keys],
            }
        )
    )
    assert len(subject) <= 160
    subject, _ = secret_card_payload(
        OwnerActionProposal(kind="secret", target="mcp_server", name="N" * 80)
    )
    assert len(subject) <= 160


def test_the_agent_chooses_fields_and_the_server_the_destination() -> None:
    card = OwnerActionProposal.model_validate(
        {
            "kind": "secret",
            "label": "Binance",
            "secret_fields": [
                {"key": "BINANCE_API_KEY", "label": "API key"},
                {"key": "BINANCE_USER", "label": "User", "secret": False},
            ],
        }
    )
    assert card.secret_fields and card.secret_fields[1].secret is False
    for bad in (
        {"label": "x"},
        {"secret_fields": [{"key": "K", "label": "k"}]},
        {"label": "x", "secret_fields": [{"key": "lower", "label": "k"}]},
        {"label": "x", "secret_fields": [{"key": "K", "label": "a"}, {"key": "K", "label": "b"}]},
        # The destination is never the agent's choice; nor are other kinds' fields.
        {"label": "x", "secret_fields": [{"key": "K", "label": "k"}], "target": "broker"},
        {"label": "x", "secret_fields": [{"key": "K", "label": "k"}], "account_id": "a"},
        # An address may carry a key: the owner types it into the card, never the agent.
        {"target": "mcp_server", "name": "Desk", "url": "https://mcp.example.test/rpc"},
        # A detail is text from chat: never blank, never longer than its connection takes.
        {"target": "broker", "metaapi_account_id": "   "},
        {"target": "news_feed", "name": "N" * 81},
    ):
        with pytest.raises(ValidationError):
            OwnerActionProposal.model_validate({"kind": "secret", **bad})
    with pytest.raises(ValidationError):
        OwnerActionProposal.model_validate(
            {"kind": "trust_source", "source_kind": "github_owner", "identifier": "x", "label": "y"}
        )


@pytest.mark.asyncio
async def test_saved_names_are_free_and_numbered_per_card() -> None:
    """A connecting card's values never take a saved name: one card's names share their
    number, and a name with no part from chat (BRAVE_API_KEY) is numbered at its end."""
    from lonora_db.secret_cards import free_names

    class Taken:
        def __init__(self, names: list[str]) -> None:
            self.names = names

        def all(self) -> list[str]:
            return self.names

    class Session:
        def __init__(self, names: list[str]) -> None:
            self.names = names

        async def scalars(self, _: object) -> Taken:
            return Taken(self.names)

    async def names(target: str, name: str, taken: list[str]) -> dict[str, str]:
        return await free_names(cast(Any, Session(taken)), "owner", target, name)

    assert await names("mcp_server", "Desk feed", []) == {
        "URL": "MCP_DESK_FEED_URL",
        "TOKEN": "MCP_DESK_FEED_TOKEN",
    }
    assert await names("mcp_server", "Desk", ["MCP_DESK_TOKEN"]) == {
        "URL": "MCP_DESK_2_URL",
        "TOKEN": "MCP_DESK_2_TOKEN",
    }
    taken = ["BRAVE_API_KEY", "BRAVE_API_KEY_2"]
    assert await names("brave_search", "Brave Search", taken) == {"API_KEY": "BRAVE_API_KEY_3"}
    assert await names("news_feed", "رويترز", []) == {"URL": "FEED_SOURCE_URL"}


def test_an_address_is_checked_before_anything_is_read() -> None:
    from lonora_api.routes.secret_cards import https_address

    assert https_address("https://mcp.example.test/rpc?k=1", "mcp_url_invalid")
    for bad in (
        "http://mcp.example.test/rpc",
        "https://user:pw@mcp.example.test/rpc",
        "https://a..b/x",
        "https://" + "a" * 64 + ".example/x",
        "https://mcp.example.test:8443/rpc",
        "https://mcp.example.test/rpc#part",
        "https://[abc/rpc",
    ):
        with pytest.raises(LonoraError) as refused:
            https_address(bad, "mcp_url_invalid")
        assert refused.value.code == "mcp_url_invalid", bad


def test_a_connecting_cards_key_is_trimmed_and_must_be_sendable() -> None:
    """A paste often adds a space or a line break: a connecting card's address, key or
    token is trimmed; a key or token no HTTP header can carry is refused. An agent's own
    card keeps its values as typed."""
    from lonora_db.secret_cards import card_values

    def row(fields: list[dict[str, Any]]) -> Any:
        return cast(Any, type("Row", (), {"payload": {"fields": fields}})())

    server = row(
        [
            {"key": "URL", "role": "server_url", "required": True},
            {"key": "TOKEN", "role": "token", "required": False},
        ]
    )
    typed = {"URL": " https://x.example/rpc\n", "TOKEN": "abc\n"}
    assert card_values(server, typed) == {"URL": "https://x.example/rpc", "TOKEN": "abc"}
    assert card_values(server, {"URL": "https://x.example/rpc", "TOKEN": "  "}) == {
        "URL": "https://x.example/rpc"
    }
    for bad in ("a b", "abc\u200b", "\u043a\u043b\u044e\u0447"):
        with pytest.raises(LonoraError) as refused:
            card_values(server, {"URL": "https://x.example/rpc", "TOKEN": bad})
        assert refused.value.code == "owner_action_secret_value_unsendable", bad
    own = row([{"key": "PASS", "role": None, "required": True}])
    assert card_values(own, {"PASS": " pass phrase "}) == {"PASS": " pass phrase "}


@pytest.mark.asyncio
async def test_a_stored_address_is_read_only_on_the_host_it_was_saved_with() -> None:
    """A feed's or calendar's address saved from a Secret card is used only while it is
    on the host the row (and the owner's trust) names."""
    from lonora_db.integrations import source_url

    row = {"type": "news_feed", "secret_id": "s", "domain": "news.example"}

    async def saved(_: str) -> str:
        return " https://news.example/rss?key=k1 "

    async def moved(_: str) -> str:
        return "https://elsewhere.example/rss"

    async def broken(_: str) -> str:
        return "https://[abc/feed"

    assert await source_url(row, saved) == "https://news.example/rss?key=k1"
    for read in (moved, broken):
        with pytest.raises(LonoraError) as changed:
            await source_url(row, read)
        assert changed.value.code == "integration_source_changed"


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The Secret card uses the PostgreSQL test database.")


async def thread_cards(fixture: Any, thread_id: str) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]], await fixture.request("GET", "/owner-actions?thread_id=" + thread_id)
    )


async def call(context: Any, tool: str, /, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=tool, arguments=arguments), context
    )


async def workspace(fixture: Any) -> dict[str, str]:
    return await fixture.runtime.services(fixture.owner).secrets.workspace_values()


@pytest.mark.asyncio
async def test_the_owner_saves_values_the_agent_never_sees() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    key, other = ("EXCHANGE_" + uuid4().hex[:6].upper() for _ in range(2))
    value, second = ("v-" + uuid4().hex for _ in range(2))
    try:
        agent = await fixture.agent("Keys")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        fields = [{"key": key, "label": "مفتاح API"}, {"key": other, "label": "Secret"}]
        proposed = await call(
            context, "owner_action_propose", kind="secret", label="بورصة", secret_fields=fields
        )
        card_id = proposed["owner_action"]["id"]
        cards = await thread_cards(fixture, context.thread_id)
        card = next(item for item in cards if item["id"] == card_id)
        assert card["kind"] == "secret" and card["status"] == "pending"
        assert card["facts"]["secret"] == {
            "label": "بورصة",
            "connect": None,
            "service": None,
            "details": {},
            "fields": [
                {**field, "secret": True, "role": None, "required": True} for field in fields
            ],
            "destination": "workspace",
            "agent_name": agent["name"],
            "saves_as": [key, other],
            "replaces": [],
        }

        # A plain confirmation carries no values; wrong keys save nothing.
        confirm = await fixture.client.post(
            f"/api/owner-actions/{card_id}/decision", json={"decision": "confirm"}
        )
        assert confirm.status_code == 422
        assert confirm.json()["code"] == "owner_action_secret_values_required"
        for values in ({key: value}, {key: value, other: value, "EXTRA": "x"}):
            wrong = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret", json={"values": values}
            )
            assert wrong.status_code == 422, values
        async with fixture.runtime.db.sessions() as session:
            assert await session.scalar(select(SecretRow).where(SecretRow.name == key)) is None

        saved = await fixture.client.post(
            f"/api/owner-actions/{card_id}/secret", json={"values": {key: value, other: second}}
        )
        assert saved.status_code == 200
        assert saved.json()["status"] == "confirmed"
        assert saved.json()["result"] == {"saved": [key, other], "destination": "workspace"}
        assert (await workspace(fixture)).items() >= {key: value, other: second}.items()

        # A second submit shows the card as it is and writes nothing.
        again = await fixture.client.post(
            f"/api/owner-actions/{card_id}/secret", json={"values": {key: "x", other: "y"}}
        )
        assert again.status_code == 200 and again.json()["status"] == "confirmed"
        assert (await workspace(fixture))[key] == value

        async with fixture.runtime.db.sessions() as session:
            row = await session.get(OwnerActionRow, card_id)
            assert row is not None
            stored = json.dumps([row.payload, row.result])
            events = (
                await session.scalars(select(EventRow).where(EventRow.owner_id == fixture.owner))
            ).all()
            messages = (
                await session.scalars(
                    select(MessageRow).where(MessageRow.thread_id == context.thread_id)
                )
            ).all()
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
        haystack = (
            stored
            + json.dumps(
                [[event.payload for event in events], [m.content for m in messages]], default=str
            )
            + json.dumps([[run.prompt, run.model_metadata] for run in runs], default=str)
        )
        assert value not in haystack and second not in haystack
        # The agent continues with the keys it asked for, never a value.
        follow = [run for run in runs if run.model_metadata.get("owner_action_id") == card_id]
        assert len(follow) == 1 and "Secret card" in follow[0].prompt

        # A card for a name already saved says, in our words, that it replaces it.
        again_card = await call(
            context,
            "owner_action_propose",
            kind="secret",
            label="rotate",
            secret_fields=[{"key": key, "label": "New key"}],
        )
        listed = await thread_cards(fixture, context.thread_id)
        rotate = next(item for item in listed if item["id"] == again_card["owner_action"]["id"])
        assert rotate["facts"]["secret"]["replaces"] == [key]
        await fixture.client.post(
            f"/api/owner-actions/{rotate['id']}/decision", json={"decision": "cancel"}
        )
        # The agent's next run names no key it chose: that text has system role.
        assert key not in follow[0].prompt and value not in follow[0].prompt

        # Not now saves nothing, and a later submit does not either.
        later = await call(
            context,
            "owner_action_propose",
            kind="secret",
            label="later",
            secret_fields=[{"key": key + "_X", "label": "k"}],
        )
        later_id = later["owner_action"]["id"]
        # A value too short for the scan to find is refused; the card still waits.
        short = await fixture.client.post(
            f"/api/owner-actions/{later_id}/secret", json={"values": {key + "_X": "ab"}}
        )
        assert short.status_code == 422 and short.json()["code"] == "secret_value_too_short"
        cancelled = await fixture.client.post(
            f"/api/owner-actions/{later_id}/decision", json={"decision": "cancel"}
        )
        assert cancelled.json()["status"] == "cancelled"
        after = await fixture.client.post(
            f"/api/owner-actions/{later_id}/secret", json={"values": {key + "_X": "v"}}
        )
        assert after.status_code == 200 and after.json()["status"] == "cancelled"
        assert key + "_X" not in await workspace(fixture)

        # Only a Secret card takes values.
        other_card = await call(
            context,
            "owner_action_propose",
            kind="trust_source",
            source_kind="feed_domain",
            identifier="desk-" + uuid4().hex[:8] + ".news.example",
        )
        refused = await fixture.client.post(
            f"/api/owner-actions/{other_card['owner_action']['id']}/secret",
            json={"values": {"K": "v"}},
        )
        assert refused.status_code == 409 and refused.json()["code"] == "owner_action_not_secret"
        with pytest.raises(LonoraError):
            await call(
                context,
                "owner_action_propose",
                kind="secret",
                label="x",
                secret_fields=[{"key": "bad-name", "label": "k"}],
            )
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(SecretRow.name.startswith("EXCHANGE_"))
                )
            ).all():
                await session.delete(row)
        await fixture.close()


@pytest.mark.asyncio
async def test_connecting_cards_take_details_from_chat_and_the_secret_from_the_owner() -> None:
    """A broker card's token goes to the broker scope with the connection, in one
    transaction; an MCP card's token is a workspace secret under a name no other
    connection holds."""
    database()
    from unittest.mock import AsyncMock, patch

    from check_streaming import Fixture
    from lonora_db.schema import BrokerSessionRow, McpConnectionRow

    fixture = await Fixture().open()
    token = "metaapi-" + uuid4().hex
    account = "acct-" + uuid4().hex[:10]
    connections: list[str] = []
    servers: list[str] = []
    try:
        agent = await fixture.agent("Desk")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        broker = await call(
            context,
            "owner_action_propose",
            kind="secret",
            target="broker",
            metaapi_account_id=account,
        )
        card_id = broker["owner_action"]["id"]
        cards = await thread_cards(fixture, context.thread_id)
        card = next(item for item in cards if item["id"] == card_id)
        facts = card["facts"]["secret"]
        assert facts["connect"] == "broker" and facts["destination"] == "broker"
        assert facts["details"] == {"metaapi_account_id": account}
        assert [field["key"] for field in facts["fields"]] == ["METAAPI_TOKEN"]
        identity = {"login": "777", "server": "Fixture-MT5", "platform": "mt5", "broker": "B"}
        with patch(
            "lonora_trading.connections.verified_identity", AsyncMock(return_value=identity)
        ):
            saved = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret", json={"values": {"METAAPI_TOKEN": token}}
            )
        assert saved.status_code == 200 and saved.json()["status"] == "confirmed"
        assert saved.json()["result"] == {"target": "broker", "configured": True, "saved": []}
        async with fixture.runtime.db.sessions() as session:
            rows = (
                await session.scalars(
                    select(BrokerSessionRow).where(BrokerSessionRow.owner_id == fixture.owner)
                )
            ).all()
            mine = [row for row in rows if row.payload.get("account_id") == account]
            assert len(mine) == 1
            connections.append(mine[0].id)
            stored = await session.get(SecretRow, mine[0].payload["secret_id"])
            assert stored is not None and stored.scope == "broker"
        # The token is the broker's: never a workspace secret.
        assert token not in (await workspace(fixture)).values()

        # An MCP server: the agent gives its name from chat; the owner types its address
        # (it may carry a key) and an optional token into the card. Both are workspace
        # secrets, each server's under names of its own.
        names: list[list[str]] = []
        addresses: list[str] = []
        # An agent's own card raised before a server takes its name.
        early = await call(
            context,
            "owner_action_propose",
            kind="secret",
            label="early",
            secret_fields=[{"key": "MCP_DESK_FEED_2_URL", "label": "k"}],
        )
        for _ in range(2):
            proposed = await call(
                context,
                "owner_action_propose",
                kind="secret",
                target="mcp_server",
                name="Desk feed",
            )
            card_id = proposed["owner_action"]["id"]
            listed = await thread_cards(fixture, context.thread_id)
            facts = next(item for item in listed if item["id"] == card_id)["facts"]["secret"]
            assert [field["key"] for field in facts["fields"]] == ["URL", "TOKEN"]
            assert facts["details"] == {"name": "Desk feed"} and len(facts["saves_as"]) == 2
            address = f"https://mcp-{uuid4().hex[:6]}.example.test/rpc?key={uuid4().hex}"
            addresses.append(address)
            done = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret",
                json={"values": {"URL": address, "TOKEN": "t-" + uuid4().hex}},
            )
            assert done.json()["status"] == "confirmed"
            result = done.json()["result"]
            # Its tools were read before the transaction (no such host): what follows is
            # settled in the transaction that saved the server.
            assert result["review"] in {"unread", "disabled"}
            assert result["saved"] == facts["saves_as"]
            # A saved card shows the names it saved, not the next free ones.
            assert done.json()["facts"]["secret"]["saves_as"] == result["saved"]
            assert done.json()["facts"]["secret"]["replaces"] == []
            servers.append(result["connection_id"])
            names.append(result["saved"])
        assert names[0] == ["MCP_DESK_FEED_URL", "MCP_DESK_FEED_TOKEN"]
        assert names[1] == ["MCP_DESK_FEED_2_URL", "MCP_DESK_FEED_2_TOKEN"]
        async with fixture.runtime.db.sessions() as session:
            for server_id, address in zip(servers, addresses, strict=True):
                server = await session.get(McpConnectionRow, server_id)
                assert server is not None and server.payload["url"] is None
                assert server.payload["endpoint_sha256"] == endpoint_sha256(address)
                for key in ("url_secret_id", "secret_id"):
                    secret_row = await session.get(SecretRow, server.payload[key])
                    assert secret_row is not None and secret_row.scope == "workspace"
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
            events = (
                await session.scalars(select(EventRow).where(EventRow.owner_id == fixture.owner))
            ).all()
        # The address never reaches chat, an event or a run; the agent's next run names
        # no saved name built from the name it gave (that text has system role).
        seen = json.dumps(
            [[run.prompt for run in runs], [event.payload for event in events]], default=str
        )
        assert not any(address in seen for address in addresses)
        assert "MCP_DESK" not in json.dumps([run.prompt for run in runs])

        # The early card would now replace the second server's address: it saves nothing,
        # and no new card may name a value a connection uses.
        replaced = await fixture.client.post(
            f"/api/owner-actions/{early['owner_action']['id']}/secret",
            json={"values": {"MCP_DESK_FEED_2_URL": "https://elsewhere.example.test/rpc"}},
        )
        assert replaced.status_code == 200 and replaced.json()["status"] == "expired"
        assert replaced.json()["status_reason"] == "secret_name_in_use"
        services = fixture.runtime.services(fixture.owner)
        async with fixture.runtime.db.sessions() as session:
            server = await session.get(McpConnectionRow, servers[1])
            assert server is not None
            url_secret = server.payload["url_secret_id"]
        assert await services.secrets.read(url_secret) == addresses[1]
        with pytest.raises(LonoraError) as in_use:
            await call(
                context,
                "owner_action_propose",
                kind="secret",
                label="again",
                secret_fields=[{"key": "MCP_DESK_FEED_2_TOKEN", "label": "k"}],
            )
        assert in_use.value.code == "owner_action_not_needed_secret_name_in_use"

        # A card the 0071 migration converted has no details; its conversation still
        # lists every card.
        async with fixture.runtime.db.sessions() as session, session.begin():
            converted = OwnerActionRow(
                owner_id=fixture.owner,
                agent_id=agent["id"],
                thread_id=context.thread_id,
                source="agent",
                kind="secret",
                subject="secret:mcp_server:converted-" + uuid4().hex[:8],
                payload={
                    "label": None,
                    "connect": "mcp_server",
                    "service": "x",
                    "details": {},
                    "fields": [
                        {"key": "URL", "label": None, "secret": False},
                        {"key": "TOKEN", "label": None, "secret": True},
                    ],
                    "destination": "workspace",
                },
                payload_hash="converted-" + uuid4().hex[:20],
                status="confirmed",
                result={},
                expires_at=datetime.now(UTC),
            )
            session.add(converted)
        listed = await thread_cards(fixture, context.thread_id)
        shown = next(item for item in listed if item["id"] == converted.id)
        assert shown["facts"]["secret"]["saves_as"] == []

        # Removing a server keeps the owner's secrets: only DELETE /secrets/{id} deletes
        # a stored secret (VISION.md 14.3.11).
        removed = await fixture.client.delete("/api/mcp/" + servers.pop(0))
        assert removed.status_code in {200, 204}
        assert set(names[0]) <= set(await workspace(fixture))
    finally:
        for server_id in servers:
            await fixture.client.delete("/api/mcp/" + server_id)
        for connection_id in connections:
            await fixture.client.delete("/api/trading/connections/" + connection_id)
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(SecretRow.name.startswith("MCP_DESK"))
                )
            ).all():
                await session.delete(row)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_calendar_watch_reads_a_saved_address_through_the_owners_store() -> None:
    """A calendar a Secret card saved keeps its address in the encrypted store: its watch
    reads it through the owner's store, never the broker layer's (7.2.3); without the
    owner's store the calendar is unavailable."""
    database()
    from unittest.mock import patch

    from check_streaming import Fixture
    from lonora_contracts.market_watch import Watch
    from lonora_db.schema import IntegrationRow, MarketWatchRow
    from lonora_market import watchers

    fixture = await Fixture().open()
    name = "CALENDAR_" + uuid4().hex[:6].upper() + "_URL"
    address = "https://cal-" + uuid4().hex[:6] + ".example.test/events?key=" + uuid4().hex
    read: list[str] = []

    class Calendar:
        def __init__(self, url: str) -> None:
            read.append(url)

        async def events(self) -> list[Any]:
            return []

    services = fixture.runtime.services(fixture.owner)
    secret_id = await services.secrets.write(name, address, "workspace")
    calendar_id = str(uuid4())
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            calendar = IntegrationRow(
                id=calendar_id,
                owner_id=fixture.owner,
                payload={
                    "type": "economic_calendar",
                    "name": "Desk calendar",
                    "enabled": True,
                    "secret_id": secret_id,
                    "domain": address.split("/")[2],
                },
            )
            session.add(calendar)
        config = Watch(
            kind="calendar", integration_id=calendar.id, condition="due", prompt="A release is due."
        )
        row = MarketWatchRow(owner_id=fixture.owner, agent_id=None, state={}, payload={})
        brokers = cast(Any, None)
        with patch.object(watchers, "EconomicCalendarAdapter", Calendar):
            await watchers.observe(
                fixture.runtime.db, brokers, row, config, read_secret=services.secrets.read
            )
            assert read == [address]
            with pytest.raises(LonoraError) as unavailable:
                await watchers.observe(fixture.runtime.db, brokers, row, config)
            assert unavailable.value.code == "calendar_integration_unavailable"
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for model, identifier in ((IntegrationRow, calendar_id), (SecretRow, secret_id)):
                stale = await session.get(model, identifier)
                if stale is not None:
                    await session.delete(stale)
        await fixture.close()
