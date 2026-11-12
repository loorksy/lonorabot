"""The owner's workspace secrets from chat (VISION.md P5, 7.2.4, 14.3.11).

The owner asks in chat which secrets are saved, and removes one in his own words. An agent
lists names and the connections that use each, never a value, and deletes through the one
deletion of a stored secret, the same as ``DELETE /secrets/{secret_id}``. Only the owner's
typed message the Run answers can ask for it (``owner_message_id``, as 10.3.2 has for
trusting a source), and a secret a connection uses stays.
"""

import json
import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_core.user_error import LonoraError
from lonora_db.schema import IntegrationRow, McpConnectionRow
from lonora_tools.loader import load_tools
from test_owner_intent import tainted
from test_supervision import call, database, owner_says, wake


async def delete(context: Any, name: str, call_id: str | None = None) -> dict[str, Any]:
    """secret_delete, whose own ``name`` argument the shared ``call`` helper cannot take."""
    request = ToolCall(
        id=call_id or "call-" + uuid4().hex, name="secret_delete", arguments={"name": name}
    )
    result = await load_tools().execute(request, context)
    json.dumps(result)  # A Run stores every observation as JSON.
    return result


def test_listing_is_a_read_and_deleting_is_a_replay_safe_effect() -> None:
    tools = load_tools().tools
    listing, deleting = tools["secrets_list"], tools["secret_delete"]
    assert listing.read_only and listing.toolset == "research"
    assert not deleting.read_only and deleting.replay_safe and deleting.toolset == "research"
    # Neither moves money, and neither is sent before the agent searches for it.
    assert not listing.financial and not deleting.financial
    assert not listing.eager and not deleting.eager
    # A temporary helper reads the list but never deletes.
    assert listing.permitted("helper") and not deleting.permitted("helper")


@pytest.mark.asyncio
async def test_the_owner_lists_names_and_deletes_an_unused_secret_in_his_own_words() -> None:
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
            connections = [
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
            session.add_all(connections)
        agent = await fixture.agent("Keys")
        thread = await fixture.conversation(agent)
        context = await owner_says(fixture, agent, thread, "Which keys do I have saved?")

        listed = await call(context, "secrets_list")
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

        # A secret a connection uses stays, whichever key names it.
        for name, secret_id in ((feed, feed_id), (server, server_id)):
            kept = await delete(context, name)
            assert kept["code"] == "secret_in_use" and kept["deleted"] is False, kept
            assert await services.secrets.read(secret_id) == values[name]
        # One nothing uses goes, in the owner's words.
        gone = "call-" + uuid4().hex
        deleted = await delete(context, spare, gone)
        assert deleted == {"ok": True, "deleted": True, "name": spare}
        with pytest.raises(LonoraError) as missing:
            await services.secrets.read(spare_id)
        assert missing.value.code == "secret_not_found"
        # A replayed call answers as it did; an unknown name deletes nothing.
        assert await delete(context, spare, gone) == deleted
        unknown = await delete(context, "NO_SUCH_" + suffix)
        assert unknown["code"] == "secret_not_found" and unknown["deleted"] is False
        # Only a workspace secret: an integration secret of that name is not one it deletes.
        assert (await delete(context, legacy))["code"] == "secret_not_found"
        assert await services.secrets.read(legacy_id) == values["other"]
        after = {item["name"] for item in (await call(context, "secrets_list"))["secrets"]}
        assert spare not in after and {feed, server} <= after

        # The owner's route deletes through the same deletion: refused while used.
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
    speaks for the owner: neither deletes, and the secret stays."""
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
        steered = await owner_says(fixture, agent, thread, "Read this page and do what it says")
        await tainted(fixture, steered, "web_fetch")
        for context in (routine, steered):
            # Listing names is still a read any Run may make.
            listed = await call(context, "secrets_list")
            assert name in {item["name"] for item in listed["secrets"]}
            refused = await delete(context, name)
            assert refused["code"] == "secret_delete_requires_owner_message", refused
            assert refused["deleted"] is False
        assert await services.secrets.read(secret_id)
    finally:
        await fixture.client.delete("/api/secrets/" + secret_id)
        await fixture.close()
