"""Saved MCP directory and unconfigured web search; no external MCP or search calls."""

import asyncio

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools


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
                    "url": "https://mcp.example.test/rpc",
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
    finally:
        if connection_id:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
