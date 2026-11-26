"""Third-party tool results never carry a stored secret's value (VISION.md 7.2.6, P1-02).

An MCP server or a web page can echo what Lonora sent it, or anything else it holds. Every
result of a tool whose content someone other than the owner wrote passes the owner's
secret scan before it reaches the model, a stored tool result or an effect receipt, and
is marked as data (``_provenance``). Runs on the real migrated PostgreSQL schema (skipped
without ``LONORA_DATABASE_URL``); the MCP server and the web page are scripted.
"""

import base64
import json
from dataclasses import replace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import Contract
from lonora_db.schema import ArtifactRow, EffectReceiptRow
from lonora_security.runtime_storage import confined_path
from lonora_tools import mcp
from lonora_tools.base import Tool
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from test_trusted_sources import SCHEMA, URL, WRITES, database

PAGE = 130_000


def leaked(text: str, value: str) -> bool:
    return value in text or base64.b64encode(value.encode()).decode() in text


class EchoServer:
    """An MCP server that writes back the bearer token it was sent, plain and in base64,
    inside a result large enough to be stored."""

    def transport(self, url: str, token: str | None = None) -> Any:
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
