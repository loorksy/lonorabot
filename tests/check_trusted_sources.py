"""Capabilities you can see: trusted sources on a fresh migrated PostgreSQL database.

1. Migration 0042 makes today's trust visible: github.com for every owner and one
   ``mcp_server`` entry per operator declaration in ``LONORA_MCP_DECLARATIONS`` (its
   endpoint and schema hashes pinned); running its seed again adds nothing; a downgrade
   drops the table and a re-upgrade seeds again.
2. Add an MCP server from chat: the agent offers a secure credential card; the owner's
   form posts the URL and token straight to the owner API; the server reads the new
   server's tools and raises the trust card (the tool that can place orders is listed as
   blocked); the owner taps Trust (read only); the agent's tool runs with no operator
   declaration, and the agent is woken to continue. The token never appears in a message,
   an event, a card or a Run.

The MCP server is scripted; no live server, broker, model provider or real order is used.
"""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.mcp.policy import endpoint_sha256, schema_sha256
from lonora_db.schema import (
    EventRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    TradingJournalRow,
    TrustedSourceRow,
)
from lonora_tools import mcp
from lonora_tools.loader import load_tools
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "packages/db/migrations/versions/0042_trusted_sources.py"
PREVIOUS = "0041_supervision_grants"
URL = "https://mcp.example.test/" + uuid4().hex[:8]
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("trusted_sources_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def alembic(action: str, revision: str, environment: dict[str, str]) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        env={**os.environ, **environment},
    )


def transport(calls: list[str]) -> Any:
    def create(url: str, token: str | None = None) -> Any:
        class Transport:
            async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
                method = payload["method"]
                calls.append(method)
                if method == "notifications/initialized":
                    return {}
                result: dict[str, Any]
                if method == "initialize":
                    result = {"protocolVersion": "2025-06-18"}
                elif method == "tools/list":
                    result = {
                        "tools": [
                            {"name": "search_posts", "inputSchema": SCHEMA},
                            {"name": "place_order", "inputSchema": SCHEMA},
                        ]
                    }
                else:
                    result = {"content": [{"type": "text", "text": "analyst posts"}]}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

            async def close(self) -> None:
                pass

        assert url == URL
        return Transport()

    return create


async def sources(fixture: Fixture, kind: str, identifier: str) -> list[TrustedSourceRow]:
    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(TrustedSourceRow).where(
                    TrustedSourceRow.owner_id == fixture.owner,
                    TrustedSourceRow.kind == kind,
                    TrustedSourceRow.identifier == identifier,
                    TrustedSourceRow.revoked_at.is_(None),
                )
            )
        )


async def seeded(fixture: Fixture, url: str) -> None:
    connection = await fixture.request(
        "POST",
        "/mcp",
        {"payload": {"name": "Declared", "transport": "http", "url": URL, "enabled": True}},
    )
    declarations = json.dumps(
        [
            {
                "owner_id": fixture.owner,
                "connection_id": connection["id"],
                "endpoint_sha256": endpoint_sha256(URL),
                "tool_name": "search_posts",
                "input_schema_sha256": schema_sha256(SCHEMA),
            }
        ]
    )
    environment = {"LONORA_MCP_DECLARATIONS": declarations}
    engine = create_async_engine(url)
    try:
        await alembic("downgrade", PREVIOUS, environment)
        async with engine.connect() as connection_:
            found = await connection_.scalar(text("SELECT to_regclass('ln_trusted_sources')"))
            assert found is None
        await alembic("upgrade", "head", environment)
        github = await sources(fixture, "github", "github.com")
        assert len(github) == 1 and github[0].added_via == "default"
        server = await sources(fixture, "mcp_server", connection["id"])
        assert len(server) == 1 and server[0].added_via == "operator"
        assert server[0].tool_hashes == {"search_posts": schema_sha256(SCHEMA)}
        assert server[0].endpoint_sha256 == endpoint_sha256(URL)
        async with engine.begin() as connection_:
            assert await connection_.run_sync(migration().seed_sources, declarations) == 0
        assert len(await sources(fixture, "mcp_server", connection["id"])) == 1
    finally:
        await engine.dispose()
        await fixture.request("DELETE", "/mcp/" + connection["id"])
    print(
        "PASS migration 0042 lists github.com and each operator declaration, re-runs add "
        "none, round trip"
    )


async def connect_and_trust(fixture: Fixture) -> None:
    token = "mcp-token-" + uuid4().hex
    calls: list[str] = []
    agent = await fixture.agent("X news")
    thread = await fixture.conversation(agent)
    context = await fixture.lease(await fixture.run(agent, thread))
    registry = load_tools()

    async def call(tool: str, /, **arguments: Any) -> dict[str, Any]:
        return await registry.execute(
            ToolCall(id="call-" + uuid4().hex, name=tool, arguments=arguments), context
        )

    card = await call(
        "owner_action_propose", kind="connect_credential", target="mcp_server", service="x"
    )
    assert card["owner_must_tap"] and not card["execution_authorized"]
    card_id = card["owner_action"]["id"]
    taps = 0
    with patch.object(mcp, "HttpMcpTransport", transport(calls)):
        # The owner's secure form: the token goes to the owner API, never to the card.
        secret = await fixture.request(
            "POST", "/integrations/secrets", {"name": "X", "value": token}
        )
        server = await fixture.request(
            "POST",
            "/mcp",
            {
                "payload": {
                    "name": "X",
                    "transport": "http",
                    "url": URL,
                    "secret_id": secret["id"],
                    "enabled": True,
                }
            },
        )
        connected = await fixture.request(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {"decision": "confirm", "connected": {"resource": "mcp", "id": server["id"]}},
        )
        taps += 1
        assert connected["status"] == "confirmed" and connected["result"]["configured"]
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", "/owner-actions?thread_id=" + thread["id"]),
        )
        trust = next(
            item for item in cards if item["kind"] == "trust_source" and item["status"] == "pending"
        )
        assert trust["facts"]["source"]["tools"] == ["search_posts"]
        assert trust["facts"]["source"]["blocked"] == ["place_order"]
        trusted = await fixture.request(
            "POST",
            f"/owner-actions/{trust['id']}/decision",
            {"decision": "confirm", "tier": "read"},
        )
        taps += 1
        assert trusted["status"] == "confirmed"
        assert context.mcp_declarations == ()
        result = await call(
            "mcp_execute",
            connection_id=server["id"],
            name="search_posts",
            arguments={"query": "gold analysts"},
        )
        assert result["result"]["content"][0]["text"] == "analyst posts"
        assert calls.count("tools/call") == 1
    assert taps == 2
    async with fixture.runtime.db.sessions() as session:
        woken = await session.scalar(
            select(func.count())
            .select_from(RunRow)
            .where(RunRow.agent_id == agent["id"], RunRow.trigger == "owner_card")
        )
        assert woken == 1, woken
        journal = await session.scalar(
            select(func.count())
            .select_from(TradingJournalRow)
            .where(TradingJournalRow.owner_id == fixture.owner)
        )
        assert journal == 0
        for model in (MessageRow, EventRow, OwnerActionRow, RunRow):
            for row in await session.scalars(select(model)):
                dumped = json.dumps({key: str(value) for key, value in vars(row).items()})
                assert token not in dumped, model.__name__
    await fixture.request("DELETE", "/mcp/" + server["id"])
    print(
        "PASS add an MCP server from chat: one secure card, one trust tap, the tool runs "
        "without a declaration, the agent continues, the token never leaves the server"
    )


async def main() -> None:
    fixture = await Fixture().open()
    try:
        await seeded(fixture, fixture.settings.database_url)
        await connect_and_trust(fixture)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
