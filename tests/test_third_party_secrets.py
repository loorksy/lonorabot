"""Third-party tool results never carry a stored secret's value (VISION.md 7.2.6, P1-02).

An MCP server or a web page can echo what Lonora sent it, or anything else it holds. Every
result of a tool whose content someone other than the owner wrote passes the owner's
secret scan before it reaches the model, a stored tool result or an effect receipt, and is
marked as data (``_provenance``). The scan is read before the call is sent. A tool that
sent a stored value scans its answer again with the values as they are now. An MCP
server's kept tool titles reach agents only through the scan. So do the results earlier
Runs checkpointed. The database cases run on the real migrated PostgreSQL schema (skipped
without ``LONORA_DATABASE_URL``); servers, pages, feeds and stores are scripted.
"""

import base64
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_db.schema import ArtifactRow, EffectReceiptRow, RunRow
from lonora_security.runtime_storage import confined_path
from lonora_security.secrets import SecretScan
from lonora_tools import feeds, market_analysis, mcp, search
from lonora_tools.base import Tool
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from test_mcp_boundary import ScriptedTransport, declaration, install_transport
from test_mcp_boundary import context as mcp_context
from test_trusted_sources import SCHEMA, URL, WRITES, database

PAGE = 130_000
# A value a titled server writes in its title, saved as a secret only after the review.
ACCOUNT = "notes-account-" + "4" * 16


def leaked(text: str, value: str) -> bool:
    return value in text or base64.b64encode(value.encode()).decode() in text


class EchoServer:
    """An MCP server that writes back the bearer token it was sent, plain and in base64,
    inside a result large enough to be stored; with ``titled``, also in its tool's title."""

    def __init__(self, *, titled: bool = False) -> None:
        self.titled = titled

    def transport(self, url: str, token: str | None = None) -> Any:
        titled = self.titled

        class Transport:
            async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
                method = payload["method"]
                if method == "notifications/initialized":
                    return {}
                result: dict[str, Any]
                if method == "initialize":
                    result = {"protocolVersion": "2025-06-18"}
                elif method == "tools/list":
                    tool = {"name": "post_note", "inputSchema": SCHEMA, "annotations": WRITES}
                    if titled:
                        tool["title"] = f"Post a note (signed in as {token}, {ACCOUNT})"
                    result = {"tools": [tool]}
                else:
                    encoded = base64.b64encode(str(token).encode()).decode()
                    text = f"saved with {token}, also {encoded}. " + "." * PAGE
                    result = {"content": [{"type": "text", "text": text}]}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

            async def close(self) -> None:
                pass

        return Transport()


@pytest.mark.asyncio
async def test_an_mcp_server_echoing_its_token_returns_only_the_marker() -> None:
    database()
    from check_streaming import Fixture
    from lonora_agent.tool_block import result_content

    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("Echo")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        name = "NOTES_TOKEN_" + uuid4().hex[:8].upper()
        token = "notes-bearer-" + uuid4().hex
        secret_id = await context.secrets.write(name, token, "integration")
        connection_id = (
            await fixture.request(
                "POST",
                "/mcp",
                {
                    "payload": {
                        "name": "Echo notes",
                        "url": URL,
                        "enabled": True,
                        "secret_id": secret_id,
                    }
                },
            )
        )["id"]
        with patch.object(mcp, "HttpMcpTransport", EchoServer().transport):
            preview = await fixture.request("POST", f"/trusted-sources/mcp/{connection_id}/preview")
            await fixture.request(
                "POST",
                f"/trusted-sources/mcp/{connection_id}",
                {"tier": "write_nonfinancial", "digest": preview["digest"]},
            )
            call = ToolCall(
                id="echo-" + uuid4().hex,
                name="mcp_execute",
                arguments={
                    "connection_id": connection_id,
                    "name": "post_note",
                    "arguments": {"query": "note"},
                },
            )
            result = await load_tools().execute(call, context)
        marker = f"[secret:{name}]"
        # What the model reads.
        shown = json.dumps(result, ensure_ascii=False)
        assert not leaked(shown, token) and shown.count(marker) == 2, shown[:300]
        assert result["_provenance"] == "third_party"
        # The effect receipt that answers a repeat of this call.
        async with fixture.runtime.db.sessions() as session:
            receipt = await session.get(
                EffectReceiptRow, mcp.receipt_key(context.for_call(call.id))
            )
            assert receipt is not None
            kept = json.dumps(receipt.result, ensure_ascii=False)
        assert not leaked(kept, token) and marker in kept
        # The stored tool result an oversized result becomes.
        summary = json.loads(await result_content(context, call, {"ok": True, **result}))
        assert summary["result_persisted"] is True, summary
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(ArtifactRow, summary["result_ref"])
            assert row is not None
        stored = confined_path(context.artifact_root, row.payload["key"]).read_text()
        assert not leaked(stored, token) and marker in stored
    finally:
        if connection_id:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


class Page(Contract):
    url: str


@pytest.mark.asyncio
async def test_a_web_result_is_scanned_and_marked_as_third_party() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reader")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        name = "PAGE_KEY_" + uuid4().hex[:8].upper()
        value = "page-key-" + uuid4().hex
        await context.secrets.write(name, value, "workspace")

        async def fetch(_: Any, args: dict[str, Any]) -> dict[str, Any]:
            return {"url": args["url"], "content": f"Your key is {value}."}

        async def note(_: Any, args: dict[str, Any]) -> dict[str, Any]:
            return {"saved": True}

        reads = {"count": 0}
        store = context.secrets
        original = store.scanned_values

        async def counted() -> dict[str, str]:
            reads["count"] += 1
            return await original()

        registry = ToolRegistry(
            [
                Tool("web_fetch", "Fetch a page", Page, fetch, True),
                Tool("fixture_note", "A first-party note", Page, note, True),
            ]
        )
        with patch.object(store, "scanned_values", counted):
            first = await registry.execute(
                ToolCall(id="page-1", name="web_fetch", arguments={"url": "https://a.test"}),
                context,
            )
            second = await registry.execute(
                ToolCall(id="page-2", name="web_fetch", arguments={"url": "https://b.test"}),
                replace(context, call_id="page-2"),
            )
            own = await registry.execute(
                ToolCall(id="note-1", name="fixture_note", arguments={"url": "x"}), context
            )
        for page in (first, second):
            assert page["content"] == f"Your key is [secret:{name}]."
            assert page["_provenance"] == "third_party"
        # A first-party result is neither scanned here nor marked.
        assert own == {"saved": True}
        # The owner's secrets are read once for the Run, not once per page.
        assert reads["count"] == 1
    finally:
        await fixture.close()


async def unreadable() -> dict[str, str]:
    raise LonoraError("secret_decryption_failed", 500)


@pytest.mark.asyncio
async def test_a_store_that_cannot_be_read_stops_an_mcp_call_before_it_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan is read before the call goes out: a store that cannot be read refuses the
    call unsent, never after a send it would then report as a plain failure (which invites
    the model to send it again)."""
    transport = ScriptedTransport()
    install_transport(monkeypatch, transport)
    context = mcp_context(declarations=(declaration(),))
    context.secrets.scanned_values = unreadable
    with pytest.raises(LonoraError, match="secret_decryption_failed"):
        await mcp.execute(
            context,
            {"connection_id": "connection", "name": "research", "arguments": {"symbol": "XAUUSD"}},
        )
    assert [call["method"] for call in transport.calls].count("tools/call") == 0


@pytest.mark.asyncio
async def test_the_registry_reads_the_scan_before_a_third_party_call_and_never_after() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Order")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        events: list[str] = []

        async def fetch(_: Any, args: dict[str, Any]) -> dict[str, Any]:
            events.append("sent")
            return {"url": args["url"], "content": "A page."}

        store = context.secrets
        original = store.scanned_values

        async def counted() -> dict[str, str]:
            events.append("read")
            return await original()

        registry = ToolRegistry([Tool("web_fetch", "Fetch a page", Page, fetch, True)])
        with patch.object(store, "scanned_values", counted):
            await registry.execute(
                ToolCall(id="order-1", name="web_fetch", arguments={"url": "https://a.test"}),
                context,
            )
        assert events == ["read", "sent"]
        # A store that cannot be read fails the call before anything is sent.
        with (
            patch.object(store, "scanned_values", unreadable),
            pytest.raises(LonoraError, match="secret_decryption_failed"),
        ):
            await registry.execute(
                ToolCall(id="order-2", name="web_fetch", arguments={"url": "https://b.test"}),
                replace(context, call_id="order-2", scans={}),
            )
        assert events == ["read", "sent"]
    finally:
        await fixture.close()


# A value the owner saved while the Run pass was going on: its scan was read before.
FRESH = "fresh-token-" + "7" * 16


def saved_during_the_pass(stored: str, **fields: Any) -> Any:
    async def read(_: str) -> str:
        return stored

    async def scanned() -> dict[str, str]:
        return {"FRESH_KEY": FRESH}

    return SimpleNamespace(
        secrets=SimpleNamespace(read=read, scanned_values=scanned),
        workspace_given=None,
        cli_tokens=None,
        scans={"owner": SecretScan({})},
        **fields,
    )


def echoed(result: dict[str, Any]) -> bool:
    """The value shows in the result, or its marker does not."""
    shown = json.dumps(result, ensure_ascii=False)
    return FRESH in shown or "[secret:FRESH_KEY]" not in shown


@pytest.mark.asyncio
async def test_a_web_search_that_sent_a_stored_key_scans_its_echo() -> None:
    context = saved_during_the_pass(FRESH, searxng_url=None)
    brave = {"type": "brave_search", "enabled": True, "secret_id": "brave"}
    answer = {
        "web": {
            "results": [
                {"title": "Echo", "url": "https://www.python.org/", "description": f"Key {FRESH}"}
            ]
        }
    }
    with (
        patch.object(search, "brave_configuration", AsyncMock(return_value=brave)),
        patch.object(search, "search_payload", AsyncMock(return_value=answer)),
    ):
        result = await search.web_search(context, {"query": "echo"})
    assert not echoed(result), result


@pytest.mark.asyncio
async def test_a_feed_read_from_its_stored_address_scans_the_echo_of_its_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = saved_during_the_pass(f"https://news.example.test/rss?token={FRESH}")
    row = SimpleNamespace(
        id="feed-1", payload={"secret_id": "feed", "domain": "news.example.test", "name": "Desk"}
    )

    async def listed(_: Any) -> list[Any]:
        return [row]

    async def fetch(url: str, limit: int) -> dict[str, Any]:
        # A feed's self link repeats the address it was read from.
        return {"status": "ok", "feed_title": "Desk " + url, "items": []}

    monkeypatch.setattr(feeds, "subscribed", listed)
    monkeypatch.setattr(feeds, "one_feed", fetch)
    result = await feeds.read(context, {})
    assert not echoed(result), result


@pytest.mark.asyncio
async def test_a_calendar_read_from_its_stored_address_scans_the_echo_of_its_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = saved_during_the_pass(
        f"https://calendar.example.test/feed?key={FRESH}", db=None, owner_id="owner"
    )
    now = utcnow()

    async def read_calendar(
        db: Any, owner_id: str, *, read_secret: Any
    ) -> tuple[list[dict[str, Any]], list[tuple[str, CalendarEvent]]]:
        address = await read_secret("calendar")
        event = CalendarEvent(
            id="cpi",
            name="CPI, from " + address,
            currency="USD",
            observed_at=now,
            scheduled_at=now + timedelta(hours=1),
            impact="high",
            source="fixture",
        )
        status = {"integration_id": "calendar", "name": "Desk", "status": "ok", "events": 1}
        return [status], [("calendar", event)]

    monkeypatch.setattr(market_analysis, "read_calendar", read_calendar)
    result = await market_analysis.calendar(context, {})
    assert result["events"] and not echoed(result), result


@pytest.mark.asyncio
async def test_mcp_tools_that_sent_the_token_scan_its_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_mcp_boundary import ADVERTISED

    described = {**ADVERTISED, "description": "Research, signed in with private-integration-token."}
    install_transport(monkeypatch, ScriptedTransport(tools=[described]))
    context = mcp_context(declarations=(declaration(),), secret_id="credential")
    # Read before the owner saved the token.
    context.scans = {"owner": SecretScan({})}
    result = await mcp.read(context, {"connection_id": "connection"})
    shown = json.dumps(result)
    assert "private-integration-token" not in shown and "[secret:RESEARCH_TOKEN]" in shown


@pytest.mark.asyncio
async def test_a_tool_title_carrying_a_stored_value_reaches_agents_as_the_marker() -> None:
    """The server's own titles are kept for the owner's views and ``capabilities_list``
    shows them to agents: a stored value inside one arrives as its marker (7.2.6), also
    one saved after the title was kept."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("Titles")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        name = "TITLED_TOKEN_" + uuid4().hex[:8].upper()
        token = "titled-bearer-" + uuid4().hex
        secret_id = await context.secrets.write(name, token, "integration")
        connection_id = (
            await fixture.request(
                "POST",
                "/mcp",
                {
                    "payload": {
                        "name": "Titled notes",
                        "url": URL,
                        "enabled": True,
                        "secret_id": secret_id,
                    }
                },
            )
        )["id"]
        with patch.object(mcp, "HttpMcpTransport", EchoServer(titled=True).transport):
            preview = await fixture.request("POST", f"/trusted-sources/mcp/{connection_id}/preview")
            await fixture.request(
                "POST",
                f"/trusted-sources/mcp/{connection_id}",
                {"tier": "write_nonfinancial", "digest": preview["digest"]},
            )
        later = "NOTES_ACCOUNT_" + uuid4().hex[:8].upper()
        await context.secrets.write(later, ACCOUNT, "workspace")
        listed = await load_tools().execute(
            ToolCall(id="capabilities-" + uuid4().hex, name="capabilities_list", arguments={}),
            context,
        )
        server = next(
            item for item in listed["mcp_servers"] if item["connection_id"] == connection_id
        )
        title = f"Post a note (signed in as [secret:{name}], [secret:{later}])"
        assert server["tool_titles"] == {"post_note": title}
        shown = json.dumps(listed, ensure_ascii=False)
        assert not leaked(shown, token) and ACCOUNT not in shown
    finally:
        if connection_id:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_earlier_runs_evidence_enters_a_new_run_scanned() -> None:
    """Results checkpointed before this scan existed, or before their value was saved as a
    secret, reach a new Run's context only through the owner's scan."""
    database()
    from check_streaming import Fixture
    from lonora_agent.context.builder import build_context

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Evidence")
        thread = await fixture.conversation(agent)
        value = "evidence-key-" + uuid4().hex
        page = ToolCall(id="w1", name="web_fetch", arguments={"url": "https://example.test/k"})
        quote = ToolCall(id="q1", name="market_quote", arguments={"symbol": "XAUUSD"})
        messages = [
            ModelMessage(role="user", content="Read the page"),
            ModelMessage(role="assistant", content="", tool_calls=[page, quote]),
            ModelMessage(
                role="tool",
                tool_call_id="w1",
                content=json.dumps({"ok": True, "content": f"The key is {value}."}),
            ),
            ModelMessage(
                role="tool",
                tool_call_id="q1",
                content=json.dumps({"ok": True, "bid": 2391.4, "note": value}),
            ),
        ]
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                RunRow(
                    thread_id=thread["id"],
                    agent_id=agent["id"],
                    status="completed",
                    execution_state={"messages": [m.model_dump(mode="json") for m in messages]},
                )
            )
        context = await fixture.lease(await fixture.run(agent, thread))
        name = "EVIDENCE_KEY_" + uuid4().hex[:8].upper()
        # Saved after both results were checkpointed.
        await context.secrets.write(name, value, "workspace")
        shown = "\n".join(message.content for message in await build_context(context))
        assert value not in shown
        # Both the retrieved page and the first-party observation.
        assert shown.count(f"[secret:{name}]") == 2, shown[-2000:]
    finally:
        await fixture.close()
