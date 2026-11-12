"""Stable bridge, frozen per-Run exposure, remembered tools, availability and shadow maps."""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_agent.context.financial_result import FINANCIAL_CALLS
from lonora_agent.executor import execute_run
from lonora_agent.runtime_notices import limit_fallback
from lonora_agent.skills.registry import CAPABILITY_TOOLS
from lonora_agent.skills.system_policy import policy_bundle
from lonora_agent.tool_batch import plan_segments
from lonora_agent.tool_exposure import remember_use, run_profiles
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import change_permission, effective_permission
from lonora_db.schema import AgentRow, EventRow, RunRow
from lonora_db.task_recovery import CHECKPOINT_TOOLS, FINANCIAL_REPLAY_TOOLS
from lonora_db.tool_usage import MAX_REMEMBERED_TOOLS, record_tool_use, remembered_tools
from lonora_tools import market_analysis, search
from lonora_tools.base import EXPOSURE_PROFILES, Tool, eager_for
from lonora_tools.context import ToolContext
from lonora_tools.loader import MODULES, load_tools
from lonora_tools.registry import BRIDGE, BRIDGE_TOOLS, ToolRegistry, proposed_names
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import (
    Arguments,
    Fixture,
    Script,
    conversation_run,
    results,
    saved_run,
)
from workspace_fake import FakeWorkspace

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
    assert "trade_execute" not in catalog.names(scope="helper")
    assert BRIDGE in catalog.names(scope="helper")


def offline_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real model_turn without routing context, image preparation or usage rows."""
    monkeypatch.setattr(model_runtime, "refresh_routing_context", AsyncMock())

    async def images(_: Any, messages: list[ModelMessage]) -> tuple[list[ModelMessage], Any]:
        return messages, {}

    monkeypatch.setattr(model_runtime, "prepare_image_observations", images)
    monkeypatch.setattr(model_runtime, "save_usage", AsyncMock())


def router(*replies: ModelReply) -> AsyncMock:
    selection = ModelSelection(provider="openai", model="offline")
    return AsyncMock(side_effect=[(reply, selection) for reply in replies])


def detached(complete: AsyncMock) -> ToolContext:
    return cast(
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


def published_text(progress: AsyncMock) -> str:
    return "".join(
        str(call.args[2]["text"])
        for call in progress.await_args_list
        if call.args[1] == "run.delta"
    )


@pytest.mark.asyncio
async def test_model_turn_resolves_bridged_financial_calls_before_the_truth_gate(
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = load_tools()
    offline_turns(monkeypatch)
    monkeypatch.setattr(model_runtime, "progress", AsyncMock())
    proposal = bridge("toolu_9", "trade_execute", {"action": "open", "side": "buy"})
    complete = router(ModelReply(text="Done: bought gold.", tool_calls=[proposal]))
    reply, _ = await model_runtime.model_turn(
        detached(complete),
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


UNRESOLVED_FINANCIAL_PROPOSALS: dict[str, ToolCall] = {
    # The common flattened slip: target arguments beside "name".
    "flattened": bridge("p", "trade_execute", None, action="open", side="buy"),
    "list_arguments": bridge("p", "trade_close_positions", ["account-1"]),
    "unparseable_arguments": bridge("p", "trade_execute", "{action: open"),
    "nested_bridge": bridge("p", BRIDGE, {"name": "trade_close_positions", "arguments": {}}),
    "hermes_batch": ToolCall(
        id="p",
        name=BRIDGE,
        arguments={"calls": json.dumps([{"name": "trade_execute", "arguments": {}}])},
    ),
    "letter_case": bridge("p", " Trade_Execute ", {"action": "open"}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", sorted(UNRESOLVED_FINANCIAL_PROPOSALS))
async def test_unresolved_bridged_financial_proposals_never_publish_premature_success(
    monkeypatch: pytest.MonkeyPatch, shape: str
):
    catalog = load_tools()
    proposal = UNRESOLVED_FINANCIAL_PROPOSALS[shape]
    # resolve_call cannot unwrap it: it fails in its handler without dispatching.
    assert catalog.resolve_call(proposal) == proposal
    assert proposed_names(proposal) & FINANCIAL_CALLS
    offline_turns(monkeypatch)
    progress = AsyncMock()
    monkeypatch.setattr(model_runtime, "progress", progress)
    wait = ToolCall(id="w", name="task_wait", arguments={"kind": "timer", "seconds": 60})
    reply, _ = await model_runtime.model_turn(
        detached(router(ModelReply(text="Done: bought gold.", tool_calls=[proposal, wait]))),
        [ModelMessage(role="user", content="Buy gold, then keep watching")],
        catalog.native_definitions(catalog.exposure(["core", "research", "task"])[0]),
        Capability.BACKGROUND,
        resolve_calls=catalog.resolve_calls,
        policy_tools=catalog.names(),
    )
    assert reply.tool_calls == [proposal, wait]
    assert reply.text == "" and published_text(progress) == ""


@pytest.mark.asyncio
async def test_a_tool_less_turn_reads_bridged_financial_proposals_with_or_without_a_resolver(
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = load_tools()
    offline_turns(monkeypatch)
    proposal = bridge("p", "trade_execute", {"action": "open", "side": "buy"})
    for resolve in (None, catalog.resolve_calls):
        progress = AsyncMock()
        monkeypatch.setattr(model_runtime, "progress", progress)
        reply, _ = await model_runtime.model_turn(
            detached(router(ModelReply(text="Done: bought gold.", tool_calls=[proposal]))),
            [ModelMessage(role="user", content="Buy gold")],
            [],
            Capability.CONVERSATION,
            resolve_calls=resolve,
        )
        assert reply.text == "" and published_text(progress) == ""


@pytest.mark.asyncio
async def test_unresolved_nonfinancial_bridge_calls_keep_their_prose(
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = load_tools()
    offline_turns(monkeypatch)
    progress = AsyncMock()
    monkeypatch.setattr(model_runtime, "progress", progress)
    lookup = bridge("q", "market_quote", None, symbol="XAUUSD")
    reply, _ = await model_runtime.model_turn(
        detached(router(ModelReply(text="Checking the latest quote.", tool_calls=[lookup]))),
        [ModelMessage(role="user", content="Gold price?")],
        [],
        Capability.CONVERSATION,
        resolve_calls=catalog.resolve_calls,
    )
    assert proposed_names(lookup) == {BRIDGE, "market_quote"}
    assert reply.text == "Checking the latest quote."
    assert published_text(progress) == reply.text


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


def test_bridged_trading_calls_are_planned_exactly_like_direct_ones():
    """Wave 1 integration: E2 bridge resolution happens before E1 planning.

    Financial tools (T2 executor) and a state writer (memory) stay serial
    barriers whether the model called them natively or through tool_call; the
    T4 evidence reads still form a parallel segment.
    """
    catalog = load_tools()
    account = {"account_id": "acct", "symbol": "XAUUSD"}
    trade = {"account_id": "acct", "symbol": "XAUUSD", "action": "buy", "volume": "0.1"}
    note = {"content": "Owner prefers London session entries"}
    block = [
        ToolCall(id="quote", name="market_quote", arguments=account),
        bridge("entry", "trade_execute", trade),
        bridge("snapshot", "market_snapshot", account),
        ToolCall(id="sessions", name="market_sessions", arguments={}),
        bridge("pause", "memory_write", note),
        bridge("flatten", "trade_close_positions", account),
        bridge("limits", "trade_record_history", {}),
        ToolCall(id="calendar", name="economic_calendar_read", arguments={}),
    ]
    resolved = catalog.resolve_calls(block)
    assert [call.id for call in resolved] == [call.id for call in block]
    assert BRIDGE not in {call.name for call in resolved}
    direct = [ToolCall(id=call.id, name=call.name, arguments=call.arguments) for call in resolved]
    planned = plan_segments(resolved, catalog.tools)
    assert planned == plan_segments(direct, catalog.tools)
    assert [(segment.kind, [call.id for call in segment.calls]) for segment in planned] == [
        ("serial", ["quote"]),
        ("serial", ["entry"]),
        ("parallel", ["snapshot", "sessions"]),
        ("serial", ["pause"]),
        ("serial", ["flatten"]),
        ("parallel", ["limits", "calendar"]),
    ]
    for name in ("trade_execute", "trade_close_positions"):
        tool = catalog.tools[name]
        assert tool.financial and not tool.runs_in_parallel() and tool.dispatch_timeout() is None
    writer = catalog.tools["memory_write"]
    assert not writer.read_only and not writer.financial and not writer.runs_in_parallel()


@pytest.mark.asyncio
async def test_a_bridged_financial_call_is_a_single_inflight_barrier_between_parallel_reads(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[str] = []
    holder: list[ToolContext] = []
    marker: dict[str, Any] = {}

    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        log.append(f"start:{args['n']}")
        await asyncio.sleep(0.03)
        log.append(f"end:{args['n']}")
        return {"n": args["n"]}

    async def trade(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        log.append("start:trade")
        environment = (await saved_run(holder[0])).execution_state["environment"]
        marker.update(single=environment["inflight"], all=environment["inflight_calls"])
        log.append("end:trade")
        return {"status": "ambiguous", "operation_id": "op-1"}

    registry = ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True, eager=eager_for("core")),
            Tool("trade_execute", "Trade", Arguments, trade, financial=True),
        ]
    )
    model = BridgingScript(
        ModelReply(
            tool_calls=[
                ToolCall(id="a", name="fixture_read", arguments={"n": 1}),
                ToolCall(id="b", name="fixture_read", arguments={"n": 2}),
                bridge("t", "trade_execute", {"n": 0}),
                ToolCall(id="c", name="fixture_read", arguments={"n": 3}),
                ToolCall(id="d", name="fixture_read", arguments={"n": 4}),
            ]
        ),
        ModelReply(text="The entry is unconfirmed; I will reconcile before anything else."),
    )
    context = await conversation_run(task_db)
    holder.append(context)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed"
    position = {entry: index for index, entry in enumerate(log)}
    assert position["start:trade"] > max(position["end:1"], position["end:2"])
    assert min(position["start:3"], position["start:4"]) > position["end:trade"]
    assert max(position["start:1"], position["start:2"]) < min(position["end:1"], position["end:2"])
    # The financial call ran alone, under its own intent marker and the model's id.
    assert marker["single"]["call_id"] == "t"
    assert [entry["call_id"] for entry in marker["all"]] == ["t"]
    assistant = [item for item in run.execution_state["messages"] if item["role"] == "assistant"]
    assert [call["name"] for call in assistant[0]["tool_calls"]].count("trade_execute") == 1
    assert results(run)["t"]["status"] == "ambiguous"


class WaitInput(BaseModel):
    kind: str = "timer"
    seconds: int = 60


def wait_stub() -> Tool:
    async def wait(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
        return {"_runtime_external_wait": {"call_id": context.call_id, "kind": "timer"}}

    return Tool("task_wait", "Wait", WaitInput, wait)


def trade_fixture(executed: list[dict[str, Any]]) -> Tool:
    async def trade(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        executed.append(args)
        return {"status": "confirmed"}

    return Tool("trade_execute", "Trade", Arguments, trade, financial=True)


async def published_deltas(context: ToolContext) -> str:
    async with context.db.sessions() as session:
        events = await session.scalars(
            select(EventRow).where(
                EventRow.run_id == context.lease.run_id, EventRow.kind == "run.delta"
            )
        )
        return "".join(str(event.payload.get("text", "")) for event in events)


@pytest.mark.asyncio
async def test_a_flattened_bridged_trade_beside_a_wait_publishes_no_success_narration(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[dict[str, Any]] = []
    registry = ToolRegistry([trade_fixture(executed), wait_stub()])
    offline_turns(monkeypatch)
    flattened = bridge("toolu_t", "trade_execute", None, n=1)
    wait = ToolCall(id="toolu_w", name="task_wait", arguments={"kind": "timer", "seconds": 60})
    complete = router(ModelReply(text="Done: bought gold.", tool_calls=[flattened, wait]))
    context = replace(
        await conversation_run(task_db), router=cast(Any, SimpleNamespace(complete=complete))
    )
    # The real model_turn and loop: the wait takes its owner update from the
    # assistant message that proposed it.
    outcome = await execute_tool_loop(context, registry, 8)
    run = await saved_run(context)
    assert outcome.external_wait and outcome.text == ""
    assert run.execution_state["environment"]["wait_update"] == {"call_id": "toolu_w", "text": ""}
    assistant = [item for item in run.execution_state["messages"] if item["role"] == "assistant"]
    assert assistant[-1]["content"] == ""
    assert assistant[-1]["tool_calls"][0]["name"] == BRIDGE
    # The malformed bridge call failed in its own handler; nothing executed.
    assert results(run)["toolu_t"]["ok"] is False and executed == []
    assert "Done" not in await published_deltas(context)


@pytest.mark.asyncio
async def test_the_tool_less_limit_report_never_publishes_a_bridged_trade_claim(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[dict[str, Any]] = []
    registry = ToolRegistry([trade_fixture(executed)])
    resolved: list[list[str]] = []
    resolve_calls = registry.resolve_calls

    def spy(calls: Sequence[ToolCall]) -> list[ToolCall]:
        result = resolve_calls(calls)
        resolved.append([call.name for call in result])
        return result

    monkeypatch.setattr(registry, "resolve_calls", spy)
    offline_turns(monkeypatch)
    proposal = bridge("toolu_f", "trade_execute", {"n": 1})
    complete = router(ModelReply(text="Done: bought gold.", tool_calls=[proposal]))
    context = replace(
        await conversation_run(task_db), router=cast(Any, SimpleNamespace(complete=complete))
    )
    # One round: the first turn is already the tool-less finish_turn report.
    await execute_run(context, registry, 120, 1)
    run = await saved_run(context)
    assert run.status == "completed" and run.model_metadata["exit_reason"] == "tool_round_limit"
    assert complete.await_args is not None and complete.await_args.args[2] == []
    # The bridged proposal was resolved for the truth gate and never executed.
    assert resolved == [["trade_execute"]] and executed == []
    assert run.result == limit_fallback(False)
    assert "Done" not in await published_deltas(context)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "account", "symbol"),
    [
        ("specialist", "account-1", "XAUUSD"),
        # The owner's default Personal Agent reads every owned account.
        ("personal", None, None),
    ],
)
async def test_trading_identities_get_the_market_working_set(
    task_db: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    account: str | None,
    symbol: str | None,
) -> None:
    db, owner, agent_id, _ = task_db
    async with db.sessions() as session, session.begin():
        agent = await session.get(AgentRow, agent_id)
        assert agent
        agent.role, agent.trading_account_id, agent.trading_symbol = role, account, symbol
    # Lonora and a root trading agent start at Ask me (W15-3); this case starts from
    # No trading, the owner's explicit choice.
    async with db.sessions() as session, session.begin():
        assert await effective_permission(session, owner, agent_id) == "supervised"
        await change_permission(
            session, owner, agent_id, PermissionChange(level="analysis", expected_revision=0)
        )
    catalog = load_tools()
    model = BridgingScript(ModelReply(text="Watching."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, catalog, 120, 8)
    exposure = (await saved_run(context)).execution_state["tool_exposure"]
    # Lonora leads every team agent by its role: it also gets the coordination set.
    personal = role == "personal"
    assert exposure["profiles"] == ["core", "market", *(["coordination"] if personal else [])]
    offered = set(model.requests[0][1])
    assert ({"agent_inspect", "peer_send"} <= offered) == personal
    assert {
        "list_accounts",
        "market_quote",
        "market_candles",
        "account_read",
        "chart_snapshot",
    } <= offered
    assert "web_search" not in offered
    # No SearXNG, browser, workspace, executor or MCP declaration in this context.
    assert exposure["unavailable"]["web_browse"] == "browser_unconfigured"
    assert exposure["unavailable"]["workspace_run"] == "workspace_unavailable"
    assert exposure["unavailable"]["mcp_execute"] == "mcp_tool_not_authorized"
    inventory = model.kwargs[0]["capability_inventory"]
    assert "web_browse=browser_unconfigured" in inventory
    financial = {"trade_execute", "trade_close_positions"}
    # No trading refuses every live mutation: the tools are named unavailable instead
    # of offered natively.
    assert "trade_execute" not in offered
    assert {name: exposure["unavailable"][name] for name in financial} == dict.fromkeys(
        financial, "agent_analysis_only"
    )
    assert "trade_execute=agent_analysis_only" in inventory
    async with db.sessions() as session, session.begin():
        await change_permission(
            session, owner, agent_id, PermissionChange(level="supervised", expected_revision=1)
        )
    supervised = BridgingScript(ModelReply(text="Ready."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", supervised)
    second = await conversation_run(task_db)
    await execute_run(second, catalog, 120, 8)
    assert "trade_execute" in set(supervised.requests[0][1])
    exposure = (await saved_run(second)).execution_state["tool_exposure"]
    assert not financial & exposure["unavailable"].keys()


def test_run_profiles_follow_the_agent_identity():
    def agent(**fields: Any) -> AgentRow:
        return AgentRow(owner_id="owner", name="Agent", **fields)

    bound = agent(role="specialist", trading_account_id="account-1", trading_symbol="XAUUSD")
    assert run_profiles(bound, False) == ["core", "market"]
    assert run_profiles(bound, True) == ["core", "market", "task"]
    # Lonora leads every team agent by its role: it inspects and messages them natively.
    assert run_profiles(agent(role="personal"), False) == ["core", "market", "coordination"]
    # A trading identity's Task Run keeps its budget for the task tools.
    assert run_profiles(agent(role="personal"), True) == ["core", "market", "task"]
    assert run_profiles(bound, False, supervises=True) == ["core", "market", "coordination"]
    assert run_profiles(agent(role="general", scope_mode="flexible"), False) == [
        "core",
        "research",
    ]
    general = agent(role="general", scope_mode="flexible")
    assert run_profiles(general, True, supervises=True) == [
        "core",
        "research",
        "coordination",
        "task",
    ]
    assert run_profiles(agent(role="delegated"), True) == ["core", "research", "task"]
    assert run_profiles(agent(role="legacy"), False) == ["core", "research"]


@pytest.mark.asyncio
async def test_a_legacy_checkpoint_keeps_every_schema_it_already_showed(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"]}

    registry = ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True, eager=eager_for("core")),
            Tool("fixture_called", "Called", Arguments, read, True),
            Tool("fixture_pending", "Pending", Arguments, read, True),
            Tool("fixture_discovered", "Discovered", Arguments, read, True),
            Tool("fixture_unseen", "Unseen", Arguments, read, True),
        ]
    )
    called = ToolCall(id="toolu_c", name="fixture_called", arguments={"n": 1})
    queued = ToolCall(id="toolu_p", name="fixture_pending", arguments={"n": 2})
    # A checkpoint written by the previous release: no tool_exposure, the
    # schemas it appended mid-Run in discovered_tool_names.
    state = {
        "messages": [
            ModelMessage(role="user", content="Analyze gold").model_dump(mode="json"),
            ModelMessage(role="assistant", content="", tool_calls=[called]).model_dump(mode="json"),
            ModelMessage(
                role="tool", tool_call_id="toolu_c", content=json.dumps({"ok": True, "n": 1})
            ).model_dump(mode="json"),
            ModelMessage(role="assistant", content="", tool_calls=[queued]).model_dump(mode="json"),
        ],
        "pending": [queued.model_dump(mode="json")],
        "instruction_skill_ids": [],
        "rounds": 2,
        "environment": {"version": 1},
        "discovered_tool_names": ["fixture_discovered", "retired_tool"],
    }
    context = await conversation_run(task_db, state)
    model = BridgingScript(ModelReply(text="Compared."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and results(run)["toolu_p"] == {"ok": True, "n": 2}
    saved = run.execution_state
    assert "discovered_tool_names" not in saved
    shown = BRIDGE_TOOLS | {"fixture_read", "fixture_called", "fixture_pending"}
    shown |= {"fixture_discovered"}
    assert saved["tool_exposure"]["native"] == [name for name in registry.tools if name in shown]
    assert set(model.requests[0][1]) == shown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("deadlock detected"),
        LonoraError("agent_not_found", 404),
        IntegrityError("INSERT INTO ln_agent_tool_usage", {}, Exception("foreign key")),
    ],
)
async def test_a_usage_recording_failure_never_changes_the_observation_or_outcome(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    writes: list[dict[str, Any]] = []
    holder: list[ToolContext] = []
    registry = fixture_registry(writes, [], holder)
    record = AsyncMock(side_effect=failure)
    monkeypatch.setattr("lonora_agent.tool_exposure.record_tool_use", record)
    model = BridgingScript(
        ModelReply(tool_calls=[bridge("toolu_w", "fixture_write", {"n": 3})]),
        ModelReply(text="Saved."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    holder.append(context)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert record.await_count == 1 and record.await_args is not None
    assert record.await_args.args[3] == "fixture_write"
    assert run.status == "completed" and run.result == "Saved." and run.error_code is None
    assert writes == [{"n": 3}] and results(run)["toolu_w"] == {"ok": True, "version": 3}


@pytest.mark.asyncio
async def test_read_only_runs_never_record_tool_usage_for_the_agent(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db

    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"]}

    registry = ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True, eager=eager_for("core")),
            Tool("fixture_lookup", "Lookup", Arguments, read, True),
        ]
    )
    model = BridgingScript(
        ModelReply(tool_calls=[bridge("toolu_l", "fixture_lookup", {"n": 2})]),
        ModelReply(text="Observed."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    async with db.sessions() as session, session.begin():
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        row.model_metadata = {**row.model_metadata, "authority": "observe_only"}
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert results(run)["toolu_l"] == {"ok": True, "n": 2}
    async with db.sessions() as session:
        assert await remembered_tools(session, owner, agent) == []

    # A subagent Run carries its parent's agent id: the same rule applies
    # before any database access.
    touched: list[str] = []

    def sessions() -> Any:
        touched.append("db")
        raise RuntimeError("database unavailable")

    probe = cast(ToolContext, SimpleNamespace(db=SimpleNamespace(sessions=sessions), owner_id="o"))
    exposure = {"profiles": ["core", "research"]}
    call = ToolCall(id="toolu_l", name="fixture_lookup", arguments={"n": 2})
    await remember_use(probe, registry, exposure, call, {"ok": True}, scope="helper")
    assert touched == []
    # Outside read-only Runs a failing store is attempted once and swallowed.
    await remember_use(probe, registry, exposure, call, {"ok": True}, scope="full")
    assert touched == ["db"]


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
    monkeypatch.setattr(market_analysis, "configured_sources", AsyncMock(return_value=[]))
    bare = cast(
        ToolContext,
        SimpleNamespace(
            owner_id="owner",
            db=None,
            searxng_url=None,
            browser_url=None,
            workspace=None,
            mcp_declarations=(),
            mcp_owner_trust=False,
        ),
    )
    assert await catalog.availability(bare) == {
        "web_search": "research_provider_not_configured",
        "web_browse": "browser_unconfigured",
        "workspace_run": "workspace_unavailable",
        "workspace_processes": "workspace_unavailable",
        "workspace_stop": "workspace_unavailable",
        "workspace_file_read": "workspace_unavailable",
        "workspace_file_write": "workspace_unavailable",
        "workspace_export": "workspace_unavailable",
        "skill_package_validate": "workspace_unavailable",
        "market_candles_to_workspace": "workspace_unavailable",
        "mcp_execute": "mcp_tool_not_authorized",
        "economic_calendar_read": "economic_calendar_not_configured",
    }
    files_only = cast(
        ToolContext,
        SimpleNamespace(
            owner_id="owner",
            db=None,
            searxng_url="http://searxng.internal",
            browser_url="http://browser.internal",
            workspace=FakeWorkspace().client(),
            mcp_declarations=(),
            mcp_owner_trust=False,
        ),
    )
    assert await catalog.availability(files_only) == {
        "mcp_execute": "mcp_tool_not_authorized",
        "economic_calendar_read": "economic_calendar_not_configured",
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
            db=None,
            searxng_url=None,
            browser_url="http://browser.internal",
            workspace=FakeWorkspace().client(),
            mcp_declarations=(declaration,),
        ),
    )
    monkeypatch.setattr(search, "brave_configuration", AsyncMock(return_value={"secret_id": "s"}))
    monkeypatch.setattr(market_analysis, "configured_sources", AsyncMock(return_value=[object()]))
    assert await catalog.availability(configured) == {}

    async def broken(_: ToolContext) -> str | None:
        raise RuntimeError("health endpoint down")

    flaky = ToolRegistry(
        [Tool("fixture_read", "Read", Arguments, AsyncMock(), True, availability=broken)]
    )
    assert await flaky.availability(bare) == {}

    # A check shared by several tools depends only on the context: it runs once.
    shared = AsyncMock(return_value="fixture_unconfigured")
    family = ToolRegistry(
        [
            Tool("fixture_one", "One", Arguments, AsyncMock(), True, availability=shared),
            Tool("fixture_two", "Two", Arguments, AsyncMock(), True, availability=shared),
        ]
    )
    assert await family.availability(bare) == dict.fromkeys(
        ["fixture_one", "fixture_two"], "fixture_unconfigured"
    )
    assert shared.await_count == 1


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
