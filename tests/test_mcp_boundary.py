"""No network/process calls: operator-owned MCP declarations preserve trading authority."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from lonora_adapters.mcp.connector import McpConnector
from lonora_adapters.mcp.policy import (
    approved_schema,
    declaration_for,
    endpoint_sha256,
    schema_sha256,
    validate_input,
)
from lonora_adapters.mcp.transport import HttpMcpTransport, StdioMcpTransport
from lonora_api.routes.mcp import McpRepository
from lonora_contracts.mcp import McpToolDeclaration
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow
from lonora_tools import mcp

URL = "https://research.example.test/mcp"
SCHEMA = {
    "type": "object",
    "properties": {"symbol": {"type": "string"}},
    "required": ["symbol"],
    "additionalProperties": False,
}
ADVERTISED = {
    "name": "research",
    "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": True},
}


def declaration(**overrides: Any) -> McpToolDeclaration:
    return McpToolDeclaration.model_validate(
        {
            "owner_id": "owner",
            "connection_id": "connection",
            "endpoint_sha256": endpoint_sha256(URL),
            "tool_name": "research",
            "input_schema_sha256": schema_sha256(SCHEMA),
            "effect": "read_only",
            **overrides,
        }
    )


def context(*, declarations: tuple[McpToolDeclaration, ...] = (), **config: Any) -> Any:
    connection = SimpleNamespace(
        owner_id="owner", payload={"name": "Research", "url": URL, "enabled": True, **config}
    )
    secret = SimpleNamespace(owner_id="owner", scope="integration")
    counters = {"decrypted": 0}

    class Session:
        async def get(self, model: Any, key: str) -> Any:
            if model is McpConnectionRow:
                return connection if key == "connection" else None
            return secret if key == "credential" else None

    @asynccontextmanager
    async def sessions():
        yield Session()

    async def decrypt(_: str) -> str:
        counters["decrypted"] += 1
        return "private-integration-token"

    return SimpleNamespace(
        owner_id="owner",
        db=SimpleNamespace(sessions=sessions),
        secrets=SimpleNamespace(read=decrypt),
        mcp_declarations=declarations,
        saved_connection=connection,
        saved_secret=secret,
        counters=counters,
    )


class ScriptedTransport:
    def __init__(self, *, tools: list[dict[str, Any]] | None = None, failed: bool = False):
        self.advertised = tools if tools is not None else [ADVERTISED]
        self.failed = failed
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        method = payload["method"]
        if method == "notifications/initialized":
            return {}
        result: dict[str, Any]
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18"}
        elif method == "tools/list":
            result = {"tools": self.advertised}
        else:
            result = {"content": [{"type": "text", "text": "verified research"}]}
            if self.failed:
                result["isError"] = True
        return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

    async def close(self) -> None:
        self.closed = True


def install_transport(monkeypatch: pytest.MonkeyPatch, transport: ScriptedTransport) -> None:
    def create_transport(*args: Any) -> ScriptedTransport:
        return transport

    monkeypatch.setattr(mcp, "HttpMcpTransport", create_transport)


@pytest.mark.asyncio
async def test_operator_exact_read_declared_schema_executes_once(monkeypatch: pytest.MonkeyPatch):
    transport = ScriptedTransport()
    install_transport(monkeypatch, transport)
    result = await mcp.execute(
        context(declarations=(declaration(),)),
        {"connection_id": "connection", "name": "research", "arguments": {"symbol": "EURUSDm"}},
    )
    assert result["result"]["content"][0]["text"] == "verified research"
    assert [call["method"] for call in transport.calls].count("tools/call") == 1
    assert transport.closed


@pytest.mark.asyncio
async def test_advertisement_and_read_only_hint_never_grant_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    transport = ScriptedTransport()
    install_transport(monkeypatch, transport)
    with pytest.raises(LonoraError, match="mcp_tool_not_authorized"):
        await mcp.execute(
            context(), {"connection_id": "connection", "name": "research", "arguments": {}}
        )
    assert transport.calls == []
    discovered = await mcp.read(context(), {"connection_id": "connection"})
    assert discovered["source_trust"] == "untrusted_external_metadata"
    assert discovered["tools"][0]["execution_allowed"] is False
    approved = await mcp.read(
        context(declarations=(declaration(),)), {"connection_id": "connection"}
    )
    assert approved["tools"][0]["execution_allowed"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"owner_id": "other"},
        {"connection_id": "other"},
        {"endpoint_sha256": "0" * 64},
        {"tool_name": "other"},
    ],
)
def test_exact_owner_connection_endpoint_and_tool_are_required(change: dict[str, Any]):
    with pytest.raises(LonoraError, match="mcp_tool_not_authorized"):
        declaration_for(
            (declaration(**change),),
            owner_id="owner",
            connection_id="connection",
            url=URL,
            tool_name="research",
        )


def test_endpoint_normalization_does_not_authorize_another_resource():
    assert endpoint_sha256("https://RESEARCH.example.test:443/mcp") == endpoint_sha256(URL)
    assert endpoint_sha256(URL + "?scope=other") != endpoint_sha256(URL)
    assert endpoint_sha256(URL + "/") != endpoint_sha256(URL)
    for url in (
        "http://research.example.test/mcp",
        URL + "#fragment",
        "https://user:secret@a.test/",
    ):
        with pytest.raises(LonoraError, match="unsafe_remote_url"):
            endpoint_sha256(url)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"x": {"$ref": "https://secret.test/schema"}}},
        {"type": "object", "properties": {"x": {"$ref": "#/$defs/x"}}},
        {"type": "object", "properties": {"x": {"$dynamicRef": "https://secret.test/schema"}}},
    ],
)
def test_all_schema_references_fail_closed_without_resolution(schema: dict[str, Any]):
    with pytest.raises(LonoraError, match="mcp_schema_reference_unsupported"):
        approved_schema(
            declaration(input_schema_sha256=schema_sha256(schema)), {"inputSchema": schema}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["schema", "arguments", "remote_error"])
async def test_failure_never_returns_fake_success_or_resends(
    monkeypatch: pytest.MonkeyPatch, failure: str
):
    transport = ScriptedTransport(failed=failure == "remote_error")
    install_transport(monkeypatch, transport)
    args = {"symbol": "EURUSDm"} if failure != "arguments" else {"symbol": 42}
    declared = declaration(input_schema_sha256="0" * 64) if failure == "schema" else declaration()
    expected = {
        "schema": "mcp_schema_changed",
        "arguments": "mcp_arguments_invalid",
        "remote_error": "mcp_tool_failed",
    }[failure]
    with pytest.raises(LonoraError, match=expected):
        await mcp.execute(
            context(declarations=(declared,)),
            {
                "connection_id": "connection",
                "name": "research",
                "arguments": args,
            },
        )
    assert [call["method"] for call in transport.calls].count("tools/call") == (
        failure == "remote_error"
    )
    assert transport.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["broker", "agent:agent", "provider", "other"])
async def test_wrong_secret_purpose_denied_before_decrypt_and_network(
    monkeypatch: pytest.MonkeyPatch, scope: str
):
    transport = ScriptedTransport()
    install_transport(monkeypatch, transport)
    ctx = context(secret_id="credential")
    ctx.saved_secret.scope = scope
    with pytest.raises(LonoraError, match="mcp_credential_scope_forbidden"):
        await mcp.read(ctx, {"connection_id": "connection"})
    assert ctx.counters["decrypted"] == 0 and transport.calls == []
    async with ctx.db.sessions() as session:
        with pytest.raises(LonoraError, match="mcp_credential_scope_forbidden"):
            await McpRepository().validate_references(
                session, "owner", ctx.saved_connection.payload
            )


@pytest.mark.asyncio
async def test_stdio_discovery_and_transport_fail_before_subprocess(
    monkeypatch: pytest.MonkeyPatch,
):
    async def forbidden_spawn(*args: Any, **kwargs: Any) -> None:
        pytest.fail("owner stdio must never spawn")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    with pytest.raises(LonoraError, match="mcp_stdio_isolation_required"):
        StdioMcpTransport(["arbitrary-downloaded-server"])
    ctx = context(transport="stdio", command=["arbitrary-downloaded-server"])
    with pytest.raises(LonoraError, match="mcp_stdio_isolation_required"):
        await mcp.read(ctx, {"connection_id": "connection"})
    async with ctx.db.sessions() as session:
        with pytest.raises(LonoraError, match="mcp_stdio_isolation_required"):
            await McpRepository().validate_references(
                session, "owner", ctx.saved_connection.payload
            )


@pytest.mark.asyncio
async def test_initialize_failure_closes_transport(monkeypatch: pytest.MonkeyPatch):
    transport = ScriptedTransport()

    async def broken(payload: dict[str, Any]) -> dict[str, Any]:
        raise LonoraError("mcp_connection_timeout", 504)

    transport.request = broken
    install_transport(monkeypatch, transport)
    with pytest.raises(LonoraError, match="mcp_connection_timeout"):
        await mcp.read(context(), {"connection_id": "connection"})
    assert transport.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        {"jsonrpc": "2.0", "id": 999, "result": {}},
        {"jsonrpc": "2.0", "id": True, "result": {}},
        {"jsonrpc": "2.0", "id": 1, "result": [], "error": {}},
        {"jsonrpc": "1.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": 1},
    ],
)
async def test_malformed_protocol_cannot_be_success(reply: dict[str, Any]):
    transport = ScriptedTransport()

    async def answer(payload: dict[str, Any]) -> dict[str, Any]:
        return reply

    transport.request = answer
    with pytest.raises(LonoraError, match="mcp_response_invalid"):
        await McpConnector(transport).call("tools/list", {})


@pytest.mark.asyncio
async def test_duplicate_advertised_names_are_rejected():
    with pytest.raises(LonoraError, match="mcp_tools_invalid"):
        await McpConnector(ScriptedTransport(tools=[ADVERTISED, ADVERTISED])).tools()


def test_validation_errors_do_not_disclose_inputs_and_execute_stays_non_readonly():
    validator = approved_schema(declaration(), ADVERTISED)
    secret = "private-secret-argument"
    with pytest.raises(LonoraError) as caught:
        validate_input(validator, {"unexpected": secret})
    assert secret not in str(caught.value)
    tool = next(tool for tool in mcp.tools() if tool.name == "mcp_execute")
    assert not tool.read_only and not tool.financial and not tool.replay_safe


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["oversize", "timeout", "error"])
async def test_http_failures_are_bounded_and_never_resent(
    monkeypatch: pytest.MonkeyPatch, failure: str
):
    from lonora_adapters.mcp import transport as module

    async def public_url(url: str) -> str:
        return url

    monkeypatch.setattr(module, "validate_public_url", public_url)
    monkeypatch.setattr(module, "MAX_RESPONSE_BYTES", 100)
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("private-token-in-remote-error", request=request)
        if failure == "error":
            return httpx.Response(500, text="private-token-in-remote-error")
        return httpx.Response(200, content=b"x" * 101)

    transport = HttpMcpTransport(URL, "private-token")
    await transport.client.aclose()
    transport.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(LonoraError) as caught:
            await transport.request({"id": 1})
        assert (
            caught.value.code
            == {
                "oversize": "mcp_response_too_large",
                "timeout": "mcp_connection_timeout",
                "error": "mcp_request_failed",
            }[failure]
        )
        assert "private-token" not in str(caught.value)
        assert calls == 1
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_sse_returns_complete_result_without_waiting_for_stream_close(
    monkeypatch: pytest.MonkeyPatch,
):
    from lonora_adapters.mcp import transport as module

    async def public_url(url: str) -> str:
        return url

    monkeypatch.setattr(module, "validate_public_url", public_url)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            result: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "result": {}}
            yield ("data: " + json.dumps(result) + "\n\n").encode()
            pytest.fail("SSE response should stop consuming after matching result")

    transport = HttpMcpTransport(URL)
    await transport.client.aclose()
    transport.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=Stream()
            )
        )
    )
    try:
        assert await transport.request({"id": 1}) == {"jsonrpc": "2.0", "id": 1, "result": {}}
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_endpoint_change_rejects_before_integration_decrypt_or_initialize(
    monkeypatch: pytest.MonkeyPatch,
):
    transport = ScriptedTransport()
    install_transport(monkeypatch, transport)
    ctx = context(declarations=(declaration(),), secret_id="credential", url=URL + "?changed=1")
    with pytest.raises(LonoraError, match="mcp_tool_not_authorized"):
        await mcp.execute(ctx, {"connection_id": "connection", "name": "research", "arguments": {}})
    assert ctx.counters["decrypted"] == 0 and transport.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("description", [42, "x" * 4001])
async def test_discovery_rejects_unbounded_or_malformed_description(description: Any):
    with pytest.raises(LonoraError, match="mcp_tools_invalid"):
        await McpConnector(
            ScriptedTransport(tools=[{**ADVERTISED, "description": description}])
        ).tools()


@pytest.mark.asyncio
async def test_disable_during_discovery_prevents_send(monkeypatch: pytest.MonkeyPatch):
    ctx = context(declarations=(declaration(),))

    class DisablingTransport(ScriptedTransport):
        async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
            result = await super().request(payload)
            if payload["method"] == "tools/list":
                ctx.saved_connection.payload["enabled"] = False
            return result

    transport = DisablingTransport()
    install_transport(monkeypatch, transport)
    with pytest.raises(LonoraError, match="mcp_disabled"):
        await mcp.execute(
            ctx,
            {"connection_id": "connection", "name": "research", "arguments": {"symbol": "EURUSDm"}},
        )
    assert transport.closed and all(call["method"] != "tools/call" for call in transport.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["initialize", "tools"])
async def test_protocol_phase_budget_has_stable_error_and_no_retry(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
):
    from lonora_adapters.mcp import connector as module

    monkeypatch.setattr(module, "PROTOCOL_TIMEOUT_SECONDS", 0.001)

    class WaitingTransport(ScriptedTransport):
        async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.calls.append(payload)
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    transport = WaitingTransport()
    adapter = McpConnector(transport)
    with pytest.raises(LonoraError, match="mcp_connection_timeout"):
        if method == "initialize":
            await adapter.initialize()
        else:
            await adapter.tools()
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_compressed_response_rejected_before_decode_or_consumption(
    monkeypatch: pytest.MonkeyPatch,
):
    from lonora_adapters.mcp import transport as module

    async def public_url(url: str) -> str:
        return url

    monkeypatch.setattr(module, "validate_public_url", public_url)

    class CompressedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail("compressed stream must not be consumed or decompressed")
            yield b"unreachable"

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=CompressedStream())

    transport = HttpMcpTransport(URL)
    await transport.client.aclose()
    transport.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(LonoraError, match="mcp_response_encoding_unsupported"):
            await transport.request({"id": 1})
    finally:
        await transport.close()
