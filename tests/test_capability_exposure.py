"""Stable bridge, frozen per-Run exposure, remembered tools, availability and shadow maps."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_agent.context.financial_result import FINANCIAL_CALLS
from lonora_agent.executor import execute_run
from lonora_agent.skills.registry import CAPABILITY_TOOLS
from lonora_agent.skills.system_policy import policy_bundle
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow
from lonora_db.task_recovery import CHECKPOINT_TOOLS, FINANCIAL_REPLAY_TOOLS
from lonora_db.tool_usage import MAX_REMEMBERED_TOOLS, record_tool_use, remembered_tools
from lonora_tools import search
from lonora_tools.base import EXPOSURE_PROFILES, Tool, eager_for
from lonora_tools.context import ToolContext
from lonora_tools.loader import MODULES, load_tools
from lonora_tools.registry import BRIDGE, BRIDGE_TOOLS, ToolRegistry
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import (
    Arguments,
    Fixture,
    Script,
    conversation_run,
    results,
    saved_run,
)

ROOT = Path(__file__).parents[1]


def bridge(identifier: str, name: Any, arguments: Any = None, **extra: Any) -> ToolCall:
    payload: dict[str, Any] = {"name": name, **extra}
    if arguments is not None:
        payload["arguments"] = arguments
    return ToolCall(id=identifier, name=BRIDGE, arguments=payload)


# ---------------------------------------------------------------- bridge


def test_bridge_resolves_to_the_exact_direct_call_and_keeps_the_call_id():
    catalog = load_tools()
    arguments = {"action": "open", "side": "buy", "symbol": "XAUUSD", "volume": 0.01}
    direct = ToolCall(id="toolu_1", name="trade_execute", arguments=arguments)
    assert catalog.resolve_call(bridge("toolu_1", "trade_execute", arguments)) == direct
    # Common model slips: JSON-string arguments, empty or missing arguments.
    assert catalog.resolve_call(bridge("a", "market_quote", json.dumps({"symbol": "X"}))) == (
        ToolCall(id="a", name="market_quote", arguments={"symbol": "X"})
    )
    assert catalog.resolve_call(bridge("b", " runtime_status ", "")).arguments == {}
    assert catalog.resolve_call(bridge("c", "runtime_status")).name == "runtime_status"
    plain = ToolCall(id="d", name="market_quote", arguments={"symbol": "X"})
    assert catalog.resolve_call(plain) is plain
    # Anything that does not name exactly one registered tool stays a bridge call.
    for unresolved in (
        bridge("e", "invented_tool", {}),
        bridge("f", "tool_call", {"name": "trade_execute", "arguments": {}}),
        bridge("g", "tool_environment", {}),
        bridge("h", "market_quote", "{not json"),
        bridge("i", "market_quote", ["symbol"]),
        bridge("j", 7, {}),
        bridge("k", "market_quote", {}, symbol="X"),
    ):
        assert catalog.resolve_call(unresolved) == unresolved
    assert catalog.resolve_calls([plain, bridge("l", "list_accounts", {})])[1].name == (
        "list_accounts"
    )


@pytest.mark.asyncio
async def test_an_unresolved_bridge_call_never_dispatches_its_target():
    ran: list[str] = []

    async def write(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        ran.append("write")
        return {}

    catalog = ToolRegistry([Tool("fixture_write", "Write", Arguments, write)])
    handler = catalog.tools[BRIDGE].handler
    for name, code in (
        ("invented", "tool_call_target_unknown"),
        ("tool_call", "tool_call_target_invalid"),
        ("fixture_write", "tool_call_unresolved"),
    ):
        with pytest.raises(LonoraError, match=code):
            await handler(cast(ToolContext, None), {"name": name, "arguments": {}})
    assert ran == []
    tool = catalog.tools[BRIDGE]
    assert tool.read_only and not tool.financial and tool.toolset == "core"


def test_read_only_scope_applies_to_the_resolved_call_exactly_as_to_a_direct_one():
    catalog = load_tools()
    resolved = catalog.resolve_call(bridge("x", "trade_execute", {}))
    assert resolved.name == "trade_execute"
    assert "trade_execute" not in catalog.names(read_only=True)
    assert BRIDGE in catalog.names(read_only=True)


@pytest.mark.asyncio
async def test_model_turn_resolves_bridged_financial_calls_before_the_truth_gate(
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = load_tools()
    monkeypatch.setattr(model_runtime, "refresh_routing_context", AsyncMock())

    async def images(_: Any, messages: list[ModelMessage]) -> tuple[list[ModelMessage], Any]:
        return messages, {}

    monkeypatch.setattr(model_runtime, "prepare_image_observations", images)
    monkeypatch.setattr(model_runtime, "progress", AsyncMock())
    monkeypatch.setattr(model_runtime, "save_usage", AsyncMock())
    proposal = bridge("toolu_9", "trade_execute", {"action": "open", "side": "buy"})
    complete = AsyncMock(
        return_value=(
            ModelReply(text="Done: bought gold.", tool_calls=[proposal]),
            ModelSelection(provider="openai", model="offline"),
        )
    )
    context = cast(
        ToolContext,
        SimpleNamespace(
            db=None,
            owner_id="owner",
            agent_id="agent",
            thread_id="thread",
            lease=SimpleNamespace(run_id="run"),
            router=SimpleNamespace(complete=complete),
        ),
    )
    reply, _ = await model_runtime.model_turn(
        context,
        [ModelMessage(role="user", content="Buy gold")],
        catalog.native_definitions(catalog.exposure(["core", "research"])[0]),
        Capability.CONVERSATION,
        resolve_calls=catalog.resolve_calls,
        policy_tools=catalog.names(),
    )
    assert [call.name for call in reply.tool_calls] == ["trade_execute"]
    assert reply.tool_calls[0].id == "toolu_9"
    # The proposed financial call has no broker outcome yet: no premature success.
    assert reply.text == ""
    assert complete.await_args is not None
    assert "trade_execute" not in {tool.name for tool in complete.await_args.args[2]}


# --------------------------------------------------------- tool loop path


class BridgingScript(Script):
    """A scripted model whose bridge calls are resolved exactly as model_turn does."""

    def __init__(self, *replies: ModelReply) -> None:
        super().__init__(*replies)
        self.kwargs: list[dict[str, Any]] = []

    async def __call__(
        self, context: Any, messages: list[ModelMessage], tools: list[Any], *args: Any, **kw: Any
    ) -> tuple[ModelReply, ModelSelection]:
        self.kwargs.append(kw)
        reply, selection = await super().__call__(context, messages, tools, *args, **kw)
        resolve = kw.get("resolve_calls")
        if resolve is not None:
            reply = reply.model_copy(update={"tool_calls": resolve(reply.tool_calls)})
        return reply, selection


def fixture_registry(
    writes: list[dict[str, Any]], markers: list[list[str]], holder: list[ToolContext]
) -> ToolRegistry:
    async def write(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        environment = (await saved_run(holder[0])).execution_state["environment"]
        markers.append([entry["call_id"] for entry in environment["inflight_calls"]])
        writes.append(args)
        return {"version": args["n"]}

    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"]}

    return ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True, eager=eager_for("core")),
            Tool("fixture_write", "Write", Arguments, write),
        ]
    )


@pytest.mark.asyncio
async def test_bridged_mutation_runs_through_the_same_effect_boundaries_and_is_remembered(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[dict[str, Any]] = []
    markers: list[list[str]] = []
    holder: list[ToolContext] = []
    registry = fixture_registry(writes, markers, holder)
    model = BridgingScript(
        ModelReply(tool_calls=[bridge("toolu_w", "fixture_write", {"n": 3})]),
        ModelReply(tool_calls=[bridge("toolu_x", "invented_tool", {})]),
        ModelReply(text="Saved."),
    )
    context = await conversation_run(task_db)
    holder.append(context)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Saved."
    # Validated arguments, one execution, intent durable before the effect.
    assert writes == [{"n": 3}] and markers == [["toolu_w"]]
    # The transcript and every scanner see the real tool, under the model's id.
    assistant = [item for item in run.execution_state["messages"] if item["role"] == "assistant"]
    assert assistant[0]["tool_calls"] == [
        {"id": "toolu_w", "name": "fixture_write", "arguments": {"n": 3}}
    ]
    observed = results(run)
    assert observed["toolu_w"] == {"ok": True, "version": 3}
    assert observed["toolu_x"]["ok"] is False
    assert observed["toolu_x"]["code"] == "tool_call_target_unknown"
    # One frozen tools array for every turn of the Run.
    offered = [names for _, names in model.requests]
    assert offered[0] == offered[1] == offered[2]
    assert set(offered[0]) == BRIDGE_TOOLS | {"fixture_read"}
    exposure = run.execution_state["tool_exposure"]
    assert exposure["profiles"] == ["core", "research"] and exposure["promoted"] == []
    assert all(kw["policy_tools"] == registry.names() for kw in model.kwargs)
    db, owner, agent, _ = task_db
    async with db.sessions() as session:
        assert await remembered_tools(session, owner, agent) == ["fixture_write"]
    # The next Run of this agent offers the remembered tool natively from turn one.
    follow_up = BridgingScript(ModelReply(text="Ready."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", follow_up)
    second = await conversation_run(task_db)
    await execute_run(second, registry, 120, 8)
    assert set(follow_up.requests[0][1]) == BRIDGE_TOOLS | {"fixture_read", "fixture_write"}
    saved = (await saved_run(second)).execution_state["tool_exposure"]
    assert saved["promoted"] == ["fixture_write"]


@pytest.mark.asyncio
async def test_an_interrupted_bridged_mutation_is_uncertain_and_never_resent(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[dict[str, Any]] = []
    holder: list[ToolContext] = []
    registry = fixture_registry(writes, [], holder)
    resolved = registry.resolve_call(bridge("toolu_m", "fixture_write", {"n": 1}))
    state = {
        "messages": [
            ModelMessage(role="user", content="Save it").model_dump(mode="json"),
            ModelMessage(role="assistant", content="", tool_calls=[resolved]).model_dump(
                mode="json"
            ),
        ],
        "pending": [resolved.model_dump(mode="json")],
        "instruction_skill_ids": [],
        "rounds": 1,
        "environment": {"version": 1, "inflight_calls": [{"call_id": "toolu_m"}]},
    }
    context = await conversation_run(task_db, state)
    holder.append(context)
    monkeypatch.setattr(
        "lonora_agent.tool_loop.model_turn", BridgingScript(ModelReply(text="Checked."))
    )
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert writes == []
    assert results(run)["toolu_m"]["code"] == "tool_execution_uncertain"


@pytest.mark.asyncio
async def test_market_agent_exposure_and_frozen_unavailable_backends(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, _, agent_id, _ = task_db
    async with db.sessions() as session, session.begin():
        agent = await session.get(AgentRow, agent_id)
        assert agent
        agent.role, agent.trading_account_id, agent.trading_symbol = (
            "specialist",
            "account-1",
            "XAUUSD",
        )
    catalog = load_tools()
    model = BridgingScript(ModelReply(text="Watching."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, catalog, 120, 8)
    exposure = (await saved_run(context)).execution_state["tool_exposure"]
    assert exposure["profiles"] == ["core", "market"]
    offered = set(model.requests[0][1])
    assert {"market_quote", "market_candles", "account_read", "trade_execute"} <= offered
    assert "web_search" not in offered and "goal_create" not in offered
    # No SearXNG, browser, workspace, executor or MCP declaration in this context.
    assert exposure["unavailable"]["web_browse"] == "browser_unconfigured"
    assert exposure["unavailable"]["workspace_execute"] == "workspace_unconfigured"
    assert exposure["unavailable"]["mcp_execute"] == "mcp_tool_not_authorized"
    inventory = model.kwargs[0]["capability_inventory"]
    assert "web_browse=browser_unconfigured" in inventory


# ------------------------------------------------------------- usage LRU


@pytest.mark.asyncio
async def test_remembered_tools_are_a_bounded_recency_list_per_agent(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    for index in range(MAX_REMEMBERED_TOOLS + 4):
        async with db.sessions() as session, session.begin():
            await record_tool_use(session, owner, agent, f"tool_{index:02d}")
    async with db.sessions() as session, session.begin():
        await record_tool_use(session, owner, agent, "tool_10")
    async with db.sessions() as session:
        names = await remembered_tools(session, owner, agent)
        assert len(names) == MAX_REMEMBERED_TOOLS
        assert names[0] == "tool_10" and names[1] == f"tool_{MAX_REMEMBERED_TOOLS + 3:02d}"
        assert "tool_00" not in names and "tool_03" not in names
        assert await remembered_tools(session, owner, "another-agent") == []
        assert await remembered_tools(session, "another-owner", agent) == []


# ----------------------------------------------------------- availability


@pytest.mark.asyncio
async def test_availability_reflects_configured_backends_and_fails_open(
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = load_tools()
    monkeypatch.setattr(search, "brave_configuration", AsyncMock(return_value=None))
    bare = cast(
        ToolContext,
        SimpleNamespace(
            owner_id="owner",
            searxng_url=None,
            browser_url=None,
            workspace_access=None,
            mcp_declarations=(),
        ),
    )
    assert await catalog.availability(bare) == {
        "web_search": "research_provider_not_configured",
        "web_browse": "browser_unconfigured",
        "workspace_export": "workspace_unconfigured",
        "workspace_inspect": "workspace_unconfigured",
        "workspace_read": "workspace_unconfigured",
        "workspace_update": "workspace_unconfigured",
        "workspace_execute": "workspace_unconfigured",
        "skill_package_validate": "workspace_unconfigured",
        "mcp_execute": "mcp_tool_not_authorized",
    }
    files_only = cast(
        ToolContext,
        SimpleNamespace(
            owner_id="owner",
            searxng_url="http://searxng.internal",
            browser_url="http://browser.internal",
            workspace_access=RunWorkspaceAccess(None),
            mcp_declarations=(),
        ),
    )
    assert await catalog.availability(files_only) == {
        "workspace_execute": "workspace_execution_unconfigured",
        "skill_package_validate": "workspace_execution_unconfigured",
        "mcp_execute": "mcp_tool_not_authorized",
    }
    declaration = McpToolDeclaration.model_validate(
        {
            "owner_id": "owner",
            "connection_id": "connection",
            "endpoint_sha256": "0" * 64,
            "tool_name": "lookup",
            "input_schema_sha256": "0" * 64,
            "effect": "read_only",
            "credential_scope": "integration",
        }
    )
    configured = cast(
        ToolContext,
        SimpleNamespace(
            owner_id="owner",
            searxng_url=None,
            browser_url="http://browser.internal",
            workspace_access=RunWorkspaceAccess(cast(Any, object())),
            mcp_declarations=(declaration,),
        ),
    )
    monkeypatch.setattr(search, "brave_configuration", AsyncMock(return_value={"secret_id": "s"}))
    assert await catalog.availability(configured) == {}

    async def broken(_: ToolContext) -> str | None:
        raise RuntimeError("health endpoint down")

    flaky = ToolRegistry(
        [Tool("fixture_read", "Read", Arguments, AsyncMock(), True, availability=broken)]
    )
    assert await flaky.availability(bare) == {}


# ------------------------------------------------------------ shadow maps


def test_every_tool_declares_a_known_toolset_and_profiles():
    catalog = load_tools()
    chapters = set(policy_bundle().sections)
    assert all(tool.toolset in chapters for tool in catalog.tools.values())
    assert set(MODULES.values()) <= chapters
    assert all(tool.eager <= set(EXPOSURE_PROFILES) for tool in catalog.tools.values())
    manifest = json.loads(
        (ROOT / "packages/agent-runtime/resources/system/manifest.json").read_text()
    )
    # The exported routing map is derived from Tool.toolset, never a second list.
    assert manifest["tool_policies"] == {name: tool.toolset for name, tool in catalog.tools.items()}


def test_hand_maintained_tool_sets_stay_consistent_with_registry_metadata():
    catalog = load_tools()
    tools = catalog.tools
    financial = {name for name, tool in tools.items() if tool.financial}
    assert FINANCIAL_CALLS == financial
    assert FINANCIAL_REPLAY_TOOLS == financial
    assert all(tools[name].replay_safe for name in FINANCIAL_REPLAY_TOOLS)
    for name in CHECKPOINT_TOOLS:
        tool = tools[name]
        assert not tool.read_only and not tool.financial and tool.replay_safe
        assert tool.toolset == "tasks"
    family_toolset = {
        "memory": "memory",
        "research": "research",
        "market": "market",
        "chart": "charts",
        "account": "account",
        "trade": "trading",
        "goal": "goals",
        "watch": "market",
        "collaboration": "collaboration",
    }
    for capability, names in CAPABILITY_TOOLS.items():
        family, verb = capability.split(".")
        assert names <= tools.keys(), capability
        assert {tools[name].toolset for name in names} == {family_toolset[family]}, capability
        if verb == "read":
            assert all(tools[name].read_only for name in names), capability
        else:
            assert any(not tools[name].read_only for name in names), capability
