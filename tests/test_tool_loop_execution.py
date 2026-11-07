"""The real tool loop: concurrent reads, barriers, crash replay, deadlines and graceful limits.

Runs on the shared ``task_db`` fixture (disposable PostgreSQL schema when
``LONORA_TASK_TEST_DATABASE_URL`` is set, otherwise in-memory SQLite) with a
scripted model in place of the provider router.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.environment import ToolRetryScheduled
from lonora_agent.executor import execute_run
from lonora_agent.runtime_notices import NO_ANSWER, is_runtime_notice
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.domain import MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskCreate, TaskStep
from lonora_db.client import Database
from lonora_db.messages import history, send_message
from lonora_db.runs import claim_next
from lonora_db.schema import EventRow, MessageRow, RunRow
from lonora_db.tasks import create_task, get_task, snapshot
from lonora_gateway.attention import candidate
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from pydantic import BaseModel
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


class Arguments(BaseModel):
    n: int = 0


class Script:
    """Scripted model turns; records what each request actually contained."""

    def __init__(self, *replies: ModelReply) -> None:
        self.replies = list(replies)
        self.requests: list[tuple[list[ModelMessage], list[str]]] = []

    async def __call__(
        self, context: Any, messages: list[ModelMessage], tools: list[Any], *args: Any, **kw: Any
    ) -> tuple[ModelReply, ModelSelection]:
        self.requests.append(
            ([item.model_copy(deep=True) for item in messages], [t.name for t in tools])
        )
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply.model_copy(deep=True), ModelSelection(provider="openai", model="scripted")


def calls(*items: tuple[str, str, int]) -> list[ToolCall]:
    return [ToolCall(id=identifier, name=name, arguments={"n": n}) for identifier, name, n in items]


def seeded(pending: list[ToolCall], **environment: Any) -> dict[str, Any]:
    messages = [
        ModelMessage(role="user", content="Analyze gold across timeframes"),
        ModelMessage(role="assistant", content="", tool_calls=pending),
    ]
    return {
        "messages": [item.model_dump(mode="json") for item in messages],
        "pending": [item.model_dump(mode="json") for item in pending],
        "instruction_skill_ids": [],
        "rounds": 1,
        "environment": {"version": 1, **environment},
    }


async def conversation_run(fixture: Fixture, state: dict[str, Any] | None = None) -> ToolContext:
    db, owner, _, thread = fixture
    async with db.sessions() as session, session.begin():
        sent = await send_message(session, owner, thread, MessageCreate(content="Analyze gold"))
        run = await claim_next(session, "loop-writer", 120, "conversation")
        assert run and run.id in sent["run_ids"]
        run.status = "running"
        run.execution_state = state or {
            "messages": [ModelMessage(role="user", content="Analyze gold").model_dump(mode="json")],
            "instruction_skill_ids": [],
        }
        lease = Lease(run_id=run.id, owner="loop-writer", fence=run.lease_fence)
    return context_for(fixture, lease, thread)


def context_for(fixture: Fixture, lease: Lease, thread: str) -> ToolContext:
    db, owner, agent, _ = fixture
    return ToolContext(
        db,
        owner,
        agent,
        thread,
        lease,
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        Path("/tmp/tool-loop-execution-fixture"),
    )


async def saved_run(context: ToolContext) -> RunRow:
    async with context.db.sessions() as session:
        run = await session.get(RunRow, context.lease.run_id)
        assert run
        return run


def results(run: RunRow) -> dict[str, dict[str, Any]]:
    return {
        str(item["tool_call_id"]): json.loads(item["content"])
        for item in run.execution_state["messages"]
        if item["role"] == "tool"
    }


def no_mid_run_system(run: RunRow) -> bool:
    roles = [item["role"] for item in run.execution_state["messages"]]
    first = next((index for index, role in enumerate(roles) if role != "system"), len(roles))
    return "system" not in roles[first:]


@pytest.mark.asyncio
async def test_independent_reads_overlap_and_results_keep_call_order(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    arrived = 0
    everyone = asyncio.Event()
    finished: list[int] = []
    inflight_seen: list[list[str]] = []
    context_holder: list[ToolContext] = []

    async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal arrived
        arrived += 1
        if arrived == 3:
            everyone.set()
        # Serial execution would never get all three handlers in at once.
        await asyncio.wait_for(everyone.wait(), 5)
        run = await saved_run(context_holder[0])
        inflight_seen.append(
            [entry["call_id"] for entry in run.execution_state["environment"]["inflight_calls"]]
        )
        await asyncio.sleep(0.02 * (4 - args["n"]))
        finished.append(args["n"])
        return {"n": args["n"], "price": 2300 + args["n"]}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    block = calls(("r1", "fixture_read", 1), ("r2", "fixture_read", 2), ("r3", "fixture_read", 3))
    context = await conversation_run(task_db, seeded(block))
    context_holder.append(context)
    model = Script(ModelReply(text="Gold is range-bound."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Gold is range-bound."
    assert finished == [3, 2, 1]
    # Intent for the whole segment was durable before any handler ran.
    assert all(sorted(seen) == ["r1", "r2", "r3"] for seen in inflight_seen)
    tool_rows = [item for item in run.execution_state["messages"] if item["role"] == "tool"]
    assert [item["tool_call_id"] for item in tool_rows] == ["r1", "r2", "r3"]
    assert [json.loads(item["content"])["n"] for item in tool_rows] == [1, 2, 3]
    assert "inflight_calls" not in run.execution_state["environment"]
    request, _ = model.requests[0]
    assert [item.tool_call_id for item in request if item.role == "tool"] == ["r1", "r2", "r3"]


@pytest.mark.asyncio
async def test_mutations_are_barriers_with_single_intent_markers(
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

    async def write(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        log.append("start:write")
        environment = (await saved_run(holder[0])).execution_state["environment"]
        marker.update(single=environment["inflight"], all=environment["inflight_calls"])
        log.append("end:write")
        return {"version": 2}

    registry = ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True),
            Tool("fixture_write", "Write", Arguments, write),
        ]
    )
    block = calls(
        ("a", "fixture_read", 1),
        ("b", "fixture_read", 2),
        ("m", "fixture_write", 0),
        ("c", "fixture_read", 3),
        ("d", "fixture_read", 4),
    )
    context = await conversation_run(task_db, seeded(block))
    holder.append(context)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Saved.")))
    await execute_run(context, registry, 120, 8)
    assert (await saved_run(context)).status == "completed"
    position = {entry: index for index, entry in enumerate(log)}
    assert position["start:write"] > max(position["end:1"], position["end:2"])
    assert min(position["start:3"], position["start:4"]) > position["end:write"]
    # Reads on either side of the barrier still overlap with each other.
    assert max(position["start:1"], position["start:2"]) < min(position["end:1"], position["end:2"])
    assert max(position["start:3"], position["start:4"]) < min(position["end:3"], position["end:4"])
    assert marker["single"]["call_id"] == "m"
    assert [entry["call_id"] for entry in marker["all"]] == ["m"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "replay_safe", "expected_runs", "code"),
    [
        # Per-call set written by this release: an interrupted read re-runs.
        ({"inflight_calls": [{"call_id": "x"}, {"call_id": "y"}]}, False, 0, None),
        # Interrupted mutation without a handler receipt is never replayed.
        ({"inflight_calls": [{"call_id": "m"}]}, False, 0, "tool_execution_uncertain"),
        # The single slot written by the previous release keeps the same rule.
        ({"inflight": {"call_id": "m"}}, False, 0, "tool_execution_uncertain"),
        # A replay-safe handler reconciles its own receipt, so it may run again.
        ({"inflight_calls": [{"call_id": "m"}]}, True, 1, None),
    ],
)
async def test_crash_recovery_replays_reads_and_never_an_uncertain_mutation(
    task_db: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, Any],
    replay_safe: bool,
    expected_runs: int,
    code: str | None,
) -> None:
    executed: list[str] = []

    async def read(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
        executed.append("read:" + context.call_id)
        return {"fresh": True}

    async def write(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
        executed.append("write:" + context.call_id)
        return {"version": 3}

    registry = ToolRegistry(
        [
            Tool("fixture_read", "Read", Arguments, read, True),
            Tool("fixture_write", "Write", Arguments, write, replay_safe=replay_safe),
        ]
    )
    block = (
        calls(("x", "fixture_read", 1), ("y", "fixture_read", 2))
        if "inflight_calls" in environment and environment["inflight_calls"][0]["call_id"] == "x"
        else calls(("m", "fixture_write", 0))
    )
    context = await conversation_run(task_db, seeded(block, **environment))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Checked.")))
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed"
    observed = results(run)
    if block[0].id == "x":
        assert sorted(executed) == ["read:x", "read:y"]
        assert observed["x"]["ok"] and observed["y"]["fresh"]
        return
    assert executed.count("write:m") == expected_runs
    assert observed["m"].get("code") == code
    if code:
        route = next(iter(run.execution_state["environment"]["routes"].values()))
        assert route["ambiguous"] is True


@pytest.mark.asyncio
async def test_read_deadline_is_a_retryable_observation(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def stuck(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(30)
        return {}

    registry = ToolRegistry(
        [Tool("fixture_read", "Read", Arguments, stuck, True, timeout_seconds=0.05)]
    )
    context = await conversation_run(task_db, seeded(calls(("slow", "fixture_read", 1))))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="unused")))
    with pytest.raises(ToolRetryScheduled):
        await execute_tool_loop(context, registry, 8)
    environment = (await saved_run(context)).execution_state["environment"]
    assert environment["retry"]["call_id"] == "slow"
    assert next(iter(environment["routes"].values()))["code"] == "tool_read_timeout"
    assert "inflight_calls" not in environment


@pytest.mark.asyncio
async def test_mutation_deadline_is_uncertain_and_never_reported_as_success(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def stuck(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(30)
        return {"version": 9}

    registry = ToolRegistry(
        [Tool("fixture_write", "Write", Arguments, stuck, timeout_seconds=0.05)]
    )
    context = await conversation_run(task_db, seeded(calls(("w", "fixture_write", 1))))
    model = Script(ModelReply(text="The update outcome is unknown."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    result = results(run)["w"]
    assert result["ok"] is False and result["code"] == "tool_execution_uncertain"
    assert result["recovery"]["next_action"] == "reconcile_before_any_resend"


@pytest.mark.asyncio
async def test_guardrail_blocks_a_no_progress_read_without_running_it(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed = 0

    async def read(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        nonlocal executed
        executed += 1
        return {"same": True}

    from lonora_agent.environment import route_key

    block = calls(("again", "fixture_read", 1))
    state = seeded(block)
    state["tool_guardrails"] = {
        "version": 1,
        "exact_failures": {},
        "tool_failures": {},
        "no_progress": {route_key(block[0]): ["digest", 5]},
        "history": [],
        "halt": None,
    }
    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    context = await conversation_run(task_db, state)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Using it.")))
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert executed == 0 and run.status == "completed"
    blocked = results(run)["again"]
    assert blocked["code"] == "guardrail_blocked" and blocked["executed"] is False


@pytest.mark.asyncio
async def test_repeating_tool_loop_halts_with_a_graceful_tool_less_reply(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed = 0

    async def write(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        nonlocal executed
        executed += 1
        return {"version": 1}

    registry = ToolRegistry([Tool("fixture_write", "Write", Arguments, write)])
    context = await conversation_run(task_db)
    replies = [
        ModelReply(tool_calls=calls((f"same-{index}", "fixture_write", 7))) for index in range(9)
    ]
    model = Script(*replies)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)

    async def final(
        context: Any, messages: list[ModelMessage], tools: list[Any], *a: Any, **k: Any
    ):
        if not tools:
            model.requests.append(([item.model_copy() for item in messages], []))
            return ModelReply(text="I applied the setting once; repeating it changed nothing."), (
                ModelSelection(provider="openai", model="scripted")
            )
        return await model(context, messages, tools, *a, **k)

    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", final)
    await execute_run(context, registry, 120, 24)
    run = await saved_run(context)
    assert run.status == "completed" and run.error_code is None
    assert executed == 5
    assert run.model_metadata["exit_reason"] == "guardrail_halt"
    assert run.result == "I applied the setting once; repeating it changed nothing."
    observed = results(run)
    assert observed["same-2"]["runtime_notice"][0]["kind"] == "tool_guardrail"
    final_request, tools = model.requests[-1]
    assert tools == [] and is_runtime_notice(final_request[-1])
    assert "repeating tool loop" in final_request[-1].content
    assert no_mid_run_system(run)


@pytest.mark.asyncio
async def test_round_limit_commits_a_final_report_instead_of_failing(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"]}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    context = await conversation_run(task_db)
    model = Script(
        ModelReply(tool_calls=calls(("t1", "fixture_read", 1))),
        ModelReply(tool_calls=calls(("t2", "fixture_read", 2))),
        ModelReply(text="Verified: two reads. Unresolved: none. Next: compare sessions."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 2)
    run = await saved_run(context)
    assert run.status == "completed" and run.error_code is None
    assert run.model_metadata["exit_reason"] == "tool_round_limit"
    assert run.result and run.result.startswith("Verified: two reads.")
    assert results(run)["t2"]["code"] == "tool_call_not_executed"
    # Budget warnings were delivered at the tail, never as mid-run system text.
    first_request, _ = model.requests[0]
    assert is_runtime_notice(first_request[-1]) and "2 model rounds" in first_request[-1].content
    second_request, _ = model.requests[1]
    assert second_request[-1].role == "tool"
    assert "1 model round" in json.loads(second_request[-1].content)["runtime_notice"][0]["message"]
    final_request, tools = model.requests[2]
    assert tools == [] and is_runtime_notice(final_request[-1])
    assert "tool-round limit" in final_request[-1].content
    assert no_mid_run_system(run)
    async with context.db.sessions() as session:
        rows = await history(session, task_db[1], task_db[3])
        assert rows[-1].content == run.result


@pytest.mark.asyncio
async def test_empty_answer_nudge_is_a_trailing_runtime_notice(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db)
    model = Script(ModelReply(text="  "), ModelReply(text="Gold trades near support."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Gold trades near support."
    second, _ = model.requests[1]
    assert is_runtime_notice(second[-1]) and NO_ANSWER.split(".")[0] in second[-1].content
    assert not any(
        item["role"] == "assistant" and not item["content"].strip()
        for item in run.execution_state["messages"]
    )
    assert no_mid_run_system(run)


async def task_run(fixture: Fixture, request: TaskCreate) -> tuple[ToolContext, str]:
    db, owner, agent, thread = fixture
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, request)
        run = await claim_next(session, "task-writer", 120, "work")
        assert run and run.id == task.payload["run_id"]
        run.status = "running"
        run.execution_state = {
            "messages": [ModelMessage(role="user", content=request.title).model_dump(mode="json")],
            "instruction_skill_ids": [],
        }
        lease = Lease(run_id=run.id, owner="task-writer", fence=run.lease_fence)
        work_thread = run.thread_id
    return context_for(fixture, lease, work_thread), task.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_body", "reason"),
    [
        (
            TaskCreate(title="Verify gold", steps=[TaskStep(id="verify", title="Verify quote")]),
            "task_steps_incomplete",
        ),
        (TaskCreate(title="Watch gold", completion_mode="continuous"), "task_wait_required"),
    ],
)
async def test_unfinished_task_gets_bounded_nudges_then_owner_attention_not_failure(
    task_db: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    request_body: TaskCreate,
    reason: str,
) -> None:
    db, owner, _, _ = task_db
    context, task_id = await task_run(task_db, request_body)
    model = Script(ModelReply(text="I looked at gold and it is done."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "waiting_input" and run.error_code is None
    assert run.execution_state["exit_reason"] == reason
    assert len(model.requests) == 3
    for request, _ in model.requests[1:]:
        assert is_runtime_notice(request[-1])
    assert no_mid_run_system(run)
    question = run.execution_state["input_requests"][-1]
    assert question["status"] == "pending" and question["question"].startswith("I looked")
    async with db.sessions() as session:
        task = await get_task(session, owner, task_id)
        projected = await snapshot(session, task)
        assert projected["status"] == "waiting"
        assert projected["waiting_reason"] == "owner_attention"
        assert task.state["task"]["status"] == "waiting"
        events = list(
            await session.scalars(
                select(EventRow).where(EventRow.kind == "task.attention_required")
            )
        )
        assert [event.payload["reason"] for event in events] == [reason]
    # The gateway revalidates the event against current Task state before notifying.
    classification, _, origin, parameters, _ = await candidate(db, cast(Any, None), events[0])
    assert (classification.importance, classification.code) == ("action_required", "task_review")
    assert parameters["task_id"] == task_id and origin == task_db[3]
    async with db.sessions() as session:
        posted = await session.scalar(
            select(MessageRow).where(
                MessageRow.thread_id == run.thread_id, MessageRow.role == "assistant"
            )
        )
        assert posted and posted.content.startswith("I looked")

    # The owner's reply resumes the SAME checkpoint with a fresh review epoch.
    async with db.sessions() as session, session.begin():
        await send_message(session, owner, run.thread_id, MessageCreate(content="Keep going."))
        resumed = await claim_next(session, "task-writer-2", 120, "work")
        assert resumed and resumed.id == run.id
        resumed.status = "running"
        lease = Lease(run_id=resumed.id, owner="task-writer-2", fence=resumed.lease_fence)
    monkeypatch.setattr("lonora_agent.tool_loop.refresh_skill_context", _no_skill_refresh)
    again = Script(ModelReply(text="Still not finished."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", again)
    await execute_run(context_for(task_db, lease, run.thread_id), ToolRegistry([]), 120, 8)
    first, _ = again.requests[0]
    assert any(item.role == "user" and item.content == "Keep going." for item in first)
    run = await saved_run(context)
    assert run.status == "waiting_input" and len(again.requests) == 3
    assert run.execution_state["input_requests"][-1]["id"] != question["id"]
    async with db.sessions() as session:
        task = await get_task(session, owner, task_id)
        assert task.state["task"]["status"] == "waiting"


async def _no_skill_refresh(*_: Any, **__: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_owner_steering_supersedes_a_queued_read_segment_before_it_runs(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, _, thread = task_db
    executed: list[str] = []

    async def read(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
        executed.append(context.call_id)
        return {"stale": True}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    block = calls(("q1", "fixture_read", 1), ("q2", "fixture_read", 2))
    context = await conversation_run(task_db, seeded(block))
    async with db.sessions() as session, session.begin():
        await send_message(session, owner, thread, MessageCreate(content="Use silver instead."))
    monkeypatch.setattr("lonora_agent.tool_loop.refresh_skill_context", _no_skill_refresh)
    model = Script(ModelReply(text="Switching to silver."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and executed == []
    assert {key: value["code"] for key, value in results(run).items()} == {
        "q1": "tool_call_superseded",
        "q2": "tool_call_superseded",
    }
    request, _ = model.requests[0]
    assert request[-1].role == "user" and request[-1].content == "Use silver instead."


@pytest.mark.asyncio
async def test_unavailable_model_at_the_limit_still_ends_gracefully(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_core.user_error import LonoraError

    async def read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"]}

    turns = 0

    async def model(
        context: Any, messages: list[ModelMessage], tools: list[Any], *a: Any, **k: Any
    ) -> tuple[ModelReply, ModelSelection]:
        nonlocal turns
        turns += 1
        if not tools:
            raise LonoraError("model_provider_unavailable", 503)
        return ModelReply(tool_calls=calls(("only", "fixture_read", 1))), ModelSelection(
            provider="openai", model="scripted"
        )

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    context = await conversation_run(task_db)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 1)
    run = await saved_run(context)
    assert turns == 2 and run.status == "completed" and run.error_code is None
    assert run.result and run.result.startswith("I stopped before finishing")
    assert run.model_metadata["exit_reason"] == "tool_round_limit"
