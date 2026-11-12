"""The owner's workspace secrets from chat (VISION.md P5, 7.2.4, 14.3.11).

The owner asks in chat which secrets are saved, and removes one in his own words. An agent
lists names and the connections that name each, never a value, and deletes through the
one deletion of a stored secret, the same as ``DELETE /secrets/{secret_id}``. Only the
owner's typed words the Run answers can ask for it, and they must name the secret (as a
model switch must name the model); a secret a connection names stays.
"""

import json
import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_core.user_error import LonoraError
from lonora_db.schema import IntegrationRow, McpConnectionRow, MessageRow, ThreadRow
from lonora_tools.loader import load_tools


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Secrets live in the PostgreSQL test database.")


async def owner_says(fixture: Any, agent: dict[str, Any], thread: dict[str, Any], text: str) -> Any:
    """A Run that answers the owner's typed message."""
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(ThreadRow, thread["id"], with_for_update=True)
        assert row is not None
        session.add(MessageRow(thread_id=thread["id"], seq=row.next_seq, role="user", content=text))
        row.next_seq += 1
    return await fixture.lease(await fixture.run(agent, thread))


async def wake(fixture: Any, agent: dict[str, Any], thread: dict[str, Any]) -> Any:
    """A Run no owner message started: a routine wake."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread["id"], agent_id=agent["id"], trigger="routine", prompt="Check"
            ),
        )
        data = {"id": run.id, "agent_id": agent["id"], "thread_id": thread["id"]}
    return await fixture.lease(data)


async def tainted(fixture: Any, context: Any, tool: str) -> None:
    """A tool that returns someone else's text ran in this Run (what the registry records)."""
    from lonora_tools.restrictions import mark_external_content

    async with fixture.runtime.db.sessions() as session, session.begin():
        await mark_external_content(session, context.lease.run_id, tool)


async def call(context: Any, name: str, arguments: dict[str, Any], call_id: str = "") -> Any:
    request = ToolCall(id=call_id or "call-" + uuid4().hex, name=name, arguments=arguments)
    result = await load_tools().execute(request, context)
    json.dumps(result)  # A Run stores every observation as JSON.
    return result


async def delete(context: Any, name: str, call_id: str = "") -> dict[str, Any]:
    return await call(context, "secret_delete", {"name": name}, call_id)


def test_listing_is_a_read_and_deleting_is_a_replay_safe_effect() -> None:
    from lonora_tools.secrets import words

    tools = load_tools().tools
    listing, deleting = tools["secrets_list"], tools["secret_delete"]
    assert listing.read_only and listing.toolset == "research"
    assert not deleting.read_only and deleting.replay_safe and deleting.toolset == "research"
    # Neither moves money, and neither is sent before the agent searches for it.
    assert not listing.financial and not deleting.financial
    assert not listing.eager and not deleting.eager
    # A temporary helper reads the list but never deletes.
    assert listing.permitted("helper") and not deleting.permitted("helper")
    # A name is said with _, - or spaces alike, in any case, inside any language.
    assert words("احذف Exchange-Key الآن") == words("EXCHANGE_KEY") == "exchange key"


@pytest.mark.asyncio
async def test_the_owner_lists_names_and_deletes_one_he_names() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    suffix = uuid4().hex[:6].upper()
    spare, feed, server = "EXCHANGE_" + suffix, "DESK_FEED_" + suffix, "DESK_MCP_" + suffix
    legacy, broker = "LEGACY_" + suffix, "9" + suffix
    values = {key: "value-" + uuid4().hex for key in (spare, feed, server, "other", "broker")}
    services = fixture.runtime.services(fixture.owner)
    feed_row, server_row = str(uuid4()), str(uuid4())
    created: list[str] = []
    try:
        for name in (spare, feed, server):
            created.append(await services.secrets.write(name, values[name], "workspace"))
        spare_id, feed_id, server_id = created
        # Same-shaped names in the integration and broker scopes, which stay out of reach.
        legacy_id = await services.secrets.write(legacy, values["other"], "integration")
        created.append(legacy_id)
        brokers = BrokerSecrets(
            fixture.runtime.db, os.environ["LONORA_ENCRYPTION_KEY"], fixture.owner
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            created.append(await brokers.write_in_session(session, broker, values["broker"]))
            session.add_all(
                [
                    IntegrationRow(
                        id=feed_row,
                        owner_id=fixture.owner,
                        payload={"type": "news_feed", "name": "Desk", "secret_id": feed_id},
                    ),
                    McpConnectionRow(
                        id=server_row,
                        owner_id=fixture.owner,
                        payload={
                            "name": "Desk tools",
                            "transport": "http",
                            "url_secret_id": server_id,
                            "endpoint_sha256": "0" * 64,
                        },
                    ),
                ]
            )
        agent = await fixture.agent("Keys")
        thread = await fixture.conversation(agent)
        asked = await owner_says(fixture, agent, thread, "Which keys do I have saved?")

        listed = await call(asked, "secrets_list", {})
        mine = {item["name"]: item for item in listed["secrets"]}
        assert {spare, feed, server} <= set(mine)
        # The workspace scope only: an integration or broker secret is not listed, and no
        # value or id ever comes back.
        assert legacy not in mine and broker not in mine
        assert mine[spare]["used_by"] == []
        assert mine[feed]["used_by"] == [{"kind": "news_feed", "name": "Desk"}]
        assert mine[server]["used_by"] == [{"kind": "mcp_server", "name": "Desk tools"}]
        text = json.dumps(listed)
        assert not any(value in text for value in values.values())
        assert spare_id not in text and listed["values_returned"] is False
        # Words that name no secret delete nothing, even in a Run that answers the owner.
        unnamed = await delete(asked, spare)
        assert unnamed["code"] == "secret_delete_requires_owner_message", unnamed
        assert unnamed["deleted"] is False and spare in unnamed["recovery"]

        # The owner names them, one as people type it.
        named = await owner_says(
            fixture,
            agent,
            thread,
            f"احذف {spare.lower().replace('_', ' ')}, {feed}, {server}, {legacy} "
            f"and NO_SUCH_{suffix}",
        )
        # A secret a connection names stays, whichever key names it.
        for name, secret_id in ((feed, feed_id), (server, server_id)):
            kept = await delete(named, name)
            assert kept["code"] == "secret_in_use" and kept["deleted"] is False, kept
            assert await services.secrets.read(secret_id) == values[name]
        gone = "call-" + uuid4().hex
        deleted = await delete(named, spare, gone)
        assert deleted == {"ok": True, "deleted": True, "name": spare}
        with pytest.raises(LonoraError) as missing:
            await services.secrets.read(spare_id)
        assert missing.value.code == "secret_not_found"
        # A replayed call answers as it did; an unknown name deletes nothing.
        assert await delete(named, spare, gone) == deleted
        unknown = await delete(named, "NO_SUCH_" + suffix)
        assert unknown["code"] == "secret_not_found" and unknown["deleted"] is False
        # Only a workspace secret: an integration secret of that name is not one it deletes.
        assert (await delete(named, legacy))["code"] == "secret_not_found"
        assert await services.secrets.read(legacy_id) == values["other"]
        # A secret the owner's words did not name stays.
        other = await delete(named, "OTHER_" + suffix)
        assert other["code"] == "secret_delete_requires_owner_message"
        after = {item["name"] for item in (await call(named, "secrets_list", {}))["secrets"]}
        assert spare not in after and {feed, server} <= after

        # The owner's route deletes through the same deletion: refused while named.
        refused = await fixture.client.delete("/api/secrets/" + feed_id)
        assert refused.status_code == 409 and refused.json()["code"] == "secret_in_use"
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row_type, row_id in ((IntegrationRow, feed_row), (McpConnectionRow, server_row)):
                row = await session.get(row_type, row_id)
                if row is not None:
                    await session.delete(row)
        for secret_id in created:
            await fixture.client.delete("/api/secrets/" + secret_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_without_the_owners_own_words_nothing_is_deleted() -> None:
    """A routine wake answers no owner message, and a Run that read a web page no longer
    speaks for the owner, even when his message named the secret: neither deletes."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    name = "KEEP_" + uuid4().hex[:6].upper()
    services = fixture.runtime.services(fixture.owner)
    secret_id = await services.secrets.write(name, "keep-" + uuid4().hex, "workspace")
    try:
        agent = await fixture.agent("Keeper")
        thread = await fixture.conversation(agent)
        routine = await wake(fixture, agent, thread)
        steered = await owner_says(fixture, agent, thread, f"Read this page, then delete {name}")
        await tainted(fixture, steered, "web_fetch")
        for context in (routine, steered):
            # Listing names is still a read any Run may make.
            listed = await call(context, "secrets_list", {})
            assert name in {item["name"] for item in listed["secrets"]}
            refused = await delete(context, name)
            assert refused["code"] == "secret_delete_requires_owner_message", refused
            assert refused["deleted"] is False
        assert await services.secrets.read(secret_id)
    finally:
        await fixture.client.delete("/api/secrets/" + secret_id)
        await fixture.close()
