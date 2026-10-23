"""Saved MCP directory and unconfigured web search; no external MCP or search calls."""

import asyncio
from dataclasses import replace
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.mcp.policy import endpoint_sha256, schema_sha256
from lonora_contracts.mcp import McpToolDeclaration
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow, SecretRow, TradeApprovalRow, TradingJournalRow
from lonora_tools import mcp
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

URL = "https://mcp.example.test/rpc"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"symbol": {"type": "string"}},
    "required": ["symbol"],
    "additionalProperties": False,
}


class ScriptedTransport:
    """No network; registry, ownership, secrets and persistence are real."""

    def __init__(self, calls: list[str]):
        self.calls = calls
        self.closed = False

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        method = payload["method"]
        self.calls.append(method)
        result: dict[str, Any]
        if method == "notifications/initialized":
            return {}
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18"}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "research",
                        "inputSchema": SCHEMA,
                        "annotations": {"readOnlyHint": True},
                    },
                    {
                        "name": "unreviewed_operation",
                        "inputSchema": SCHEMA,
                        "annotations": {"readOnlyHint": True},
                    },
                ]
            }
        else:
            assert payload["params"]["name"] == "research"
            result = {"content": [{"type": "text", "text": "scripted research result"}]}
        return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

    async def close(self) -> None:
        self.closed = True


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("MCP directory fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()
        empty = await registry.execute(
            ToolCall(id="none", name="mcp_connections", arguments={}), context, True
        )
        assert empty["connections"] == []
        try:
            await registry.execute(
                ToolCall(
                    id="missing",
                    name="mcp_tools",
                    arguments={"connection_id": "missing-connection"},
                ),
                context,
                True,
            )
        except LonoraError as error:
            assert error.code == "mcp_not_found"
        else:
            raise AssertionError("missing MCP connection was accepted")
        created = await fixture.request(
            "POST",
            "/mcp",
            {
                "payload": {
                    "name": "Fixture server",
                    "transport": "http",
                    "url": URL,
                    "command": [],
                    "enabled": False,
                }
            },
        )
        connection_id = created["id"]
        listed = await registry.execute(
            ToolCall(id="list", name="mcp_connections", arguments={}), context, True
        )
        row = next(item for item in listed["connections"] if item["connection_id"] == connection_id)
        assert (
            row["name"] == "Fixture server"
            and row["transport"] == "http"
            and row["enabled"] is False
            and row["credentials_configured"] is False
        )
        assert "secret_id" not in row and "mcp.example.test" not in str(listed)
        try:
            await registry.execute(
                ToolCall(
                    id="disabled", name="mcp_tools", arguments={"connection_id": connection_id}
                ),
                context,
                True,
            )
        except LonoraError as error:
            assert error.code == "mcp_disabled"
        else:
            raise AssertionError("disabled MCP connection was contacted")
        try:
            await registry.execute(
                ToolCall(id="search", name="web_search", arguments={"query": "fixture"}),
                context,
                True,
            )
        except LonoraError as error:
            assert error.code == "research_provider_not_configured"
        else:
            raise AssertionError("web search ran without a configured provider")
        print("PASS MCP directory hides endpoints and unconfigured web search stays explicit")

        secret_id = await context.secrets.write(
            "mcp-integration-fixture", "fixture-only", "integration"
        )
        created = await fixture.request(
            "PUT",
            "/mcp/" + connection_id,
            {
                "version": created["version"],
                "payload": {**created["payload"], "enabled": True, "secret_id": secret_id},
            },
        )
        declaration = McpToolDeclaration(
            owner_id=fixture.owner,
            connection_id=connection_id,
            endpoint_sha256=endpoint_sha256(URL),
            tool_name="research",
            input_schema_sha256=schema_sha256(SCHEMA),
        )
        approved = replace(context, mcp_declarations=(declaration,))
        calls: list[str] = []
        transports: list[ScriptedTransport] = []

        def create_transport(url: str, token: str | None = None) -> ScriptedTransport:
            assert url == URL and token == "fixture-only"
            transport = ScriptedTransport(calls)
            transports.append(transport)
            return transport

        async def execute(name: str = "research", **changes: Any) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(
                    id="external-operation",
                    name="mcp_execute",
                    arguments={
                        "connection_id": connection_id,
                        "name": name,
                        "arguments": {"symbol": "EURUSDm"},
                        **changes,
                    },
                ),
                approved,
            )

        async with fixture.runtime.db.sessions() as session:
            before_journal = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
            before_approvals = await session.scalar(
                select(func.count()).select_from(TradeApprovalRow)
            )
        with patch.object(mcp, "HttpMcpTransport", create_transport):
            found = await registry.execute(
                ToolCall(
                    id="discover",
                    name="mcp_tools",
                    arguments={"connection_id": connection_id},
                ),
                approved,
                read_only=True,
            )
            assert found["tools"][0]["execution_allowed"] is True
            assert found["tools"][1]["execution_allowed"] is False
            assert (await execute())["result"]["content"][0]["text"] == "scripted research result"
            assert calls.count("tools/call") == 1
            previous = len(calls)
            for name, arguments, code in (
                ("unreviewed_operation", {"symbol": "EURUSDm"}, "mcp_tool_not_authorized"),
                ("research", {"symbol": 1}, "mcp_arguments_invalid"),
            ):
                try:
                    await execute(name, arguments=arguments)
                except LonoraError as error:
                    assert error.code == code, error.code
                else:
                    raise AssertionError("unreviewed/invalid MCP operation executed")
                if code == "mcp_tool_not_authorized":
                    assert len(calls) == previous
            assert calls.count("tools/call") == 1

            try:
                await registry.execute(
                    ToolCall(
                        id="readonly",
                        name="mcp_execute",
                        arguments={
                            "connection_id": connection_id,
                            "name": "research",
                            "arguments": {},
                        },
                    ),
                    approved,
                    read_only=True,
                )
            except LonoraError as error:
                assert error.code == "tool_not_allowed"
            else:
                raise AssertionError("observe-only context gained external execution")

            # Resource changes revoke an otherwise valid declaration before IO.
            created = await fixture.request(
                "PUT",
                "/mcp/" + connection_id,
                {
                    "version": created["version"],
                    "payload": {**created["payload"], "url": URL + "?changed=1"},
                },
            )
            previous = len(calls)
            try:
                await execute()
            except LonoraError as error:
                assert error.code == "mcp_tool_not_authorized"
            else:
                raise AssertionError("changed endpoint retained external authority")
            assert len(calls) == previous

            # Legacy or tampered secret-purpose refs also fail before decryption.
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(McpConnectionRow, connection_id, with_for_update=True)
                secret = await session.get(SecretRow, secret_id, with_for_update=True)
                assert row is not None and secret is not None
                row.payload = {**row.payload, "url": URL}
                secret.scope = "broker"
            try:
                await execute()
            except LonoraError as error:
                assert error.code == "mcp_credential_scope_forbidden"
            else:
                raise AssertionError("broker credential accepted by MCP")
            assert len(calls) == previous
        assert all(transport.closed for transport in transports)
        async with fixture.runtime.db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == before_journal
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == before_approvals
            )
        print(
            "PASS real owner directory, exact declaration, schema and credential scope authorize only scripted read operations; no financial effects"
        )
    finally:
        if connection_id:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
