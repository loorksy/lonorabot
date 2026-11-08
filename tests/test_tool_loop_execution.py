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
from lonora_agent.automation.background import start_ticket
from lonora_agent.environment import ToolRetryScheduled
from lonora_agent.executor import execute_run
from lonora_agent.runtime_notices import NO_ANSWER, is_runtime_notice
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.domain import MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.tasks import TaskCreate, TaskStep
from lonora_db.boards import BoardRepository
from lonora_db.client import Database
from lonora_db.messages import history, send_message
from lonora_db.runs import claim_next, create_run, outcome_status
from lonora_db.schema import EventRow, MessageRow, RunRow, TicketRow
from lonora_db.tasks import create_task, get_task, snapshot
from lonora_db.tickets import TicketRepository
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
    executed: list[str] = []

    async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        executed.append(context.call_id)
        return {"n": args["n"]}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    context = await conversation_run(task_db)
    model = Script(
        ModelReply(tool_calls=calls(("t1", "fixture_read", 1))),
        ModelReply(tool_calls=calls(("t2", "fixture_read", 2))),
        ModelReply(text="Verified: two reads. Unresolved: none. Next: compare sessions."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 3)
    run = await saved_run(context)
    assert run.status == "completed" and run.error_code is None
    assert run.model_metadata["exit_reason"] == "tool_round_limit"
    assert run.result and run.result.startswith("Verified: two reads.")
    # Every round the model was offered tools in ran its calls; the third and
    # last budgeted turn is the tool-less report, not a wasted tool turn.
    assert executed == ["t1", "t2"] and len(model.requests) == 3
    assert not any(item.get("code") == "tool_call_not_executed" for item in results(run).values())
    # Budget warnings were delivered at the tail, never as mid-run system text.
    first_request, first_tools = model.requests[0]
    assert first_tools and is_runtime_notice(first_request[-1])
    assert "2 model rounds whose tool calls will execute" in first_request[-1].content
    second_request, second_tools = model.requests[1]
    assert second_tools and second_request[-1].role == "tool"
    warning = json.loads(second_request[-1].content)["runtime_notice"][0]["message"]
    assert warning.startswith("This is the last model round in this run whose tool calls")
    final_request, tools = model.requests[2]
    assert tools == [] and is_runtime_notice(final_request[-1])
    assert "tool-round limit" in final_request[-1].content
    assert no_mid_run_system(run)
    async with context.db.sessions() as session:
        rows = await history(session, task_db[1], task_db[3])
        assert rows[-1].content == run.result


@pytest.mark.asyncio
async def test_limited_ticket_and_peer_work_is_never_projected_as_completed(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A work-limit report completes the Run, but its consumers read "limited"."""
    db, owner, agent, thread = task_db

    async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        return {"n": args["n"], "partial": True}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, read, True)])
    async with db.sessions() as session, session.begin():
        board = await BoardRepository().create(session, owner, {"title": "Work"}, agent_id=agent)
        ticket = await TicketRepository().create(
            session,
            owner,
            {"board_id": board.id, "title": "Reconcile all 40 accounts", "description": ""},
            agent_id=agent,
        )
        ticket_id = ticket.id
    started = await start_ticket(db, owner, ticket_id)
    async with db.sessions() as session, session.begin():
        parent = await create_run(
            session,
            owner,
            RunRequest(thread_id=thread, agent_id=agent, trigger="user", prompt="Delegate"),
        )
        parent.status = "running"
        child = await session.get(RunRow, started["id"])
        assert child is not None
        child.parent_run_id = parent.id
        await session.flush()
        run = await claim_next(session, "ticket-writer", 120, "work")
        assert run and run.id == started["id"]
        run.status = "running"
        run.execution_state = {
            "messages": [
                ModelMessage(role="user", content="Reconcile all 40 accounts").model_dump(
                    mode="json"
                )
            ],
            "instruction_skill_ids": [],
        }
        lease = Lease(run_id=run.id, owner="ticket-writer", fence=run.lease_fence)
        ticket_thread = run.thread_id
    model = Script(
        *(ModelReply(tool_calls=calls((f"r{n}", "fixture_read", n))) for n in range(3)),
        ModelReply(text="I reconciled 3 of 40 accounts before stopping."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = context_for(task_db, lease, ticket_thread)
    await execute_run(context, registry, 120, 4)
    run = await saved_run(context)
    # The owner-visible report is committed and the Run itself ends gracefully.
    assert run.status == "completed", (run.status, run.error_code)
    assert run.model_metadata["reply_outcome"] == "limited"
    assert outcome_status(run) == "limited"
    async with db.sessions() as session:
        row = await session.get(TicketRow, ticket_id)
        assert row is not None
        # Unfinished ticket work waits to be started again; it is never "done".
        assert row.payload["status"] == "waiting"
        assert row.state["exit_reason"] == "tool_round_limit"
        assert row.state["result"] == "I reconciled 3 of 40 accounts before stopping."
        returned = await session.scalar(
            select(MessageRow).where(
                MessageRow.thread_id == thread, MessageRow.content.like("<peer_outcome%")
            )
        )
        assert returned is not None and "status='limited'" in returned.content
    # Starting the ticket again is possible: it is not left "working".
    assert (await start_ticket(db, owner, ticket_id))["trigger"] == "tickets"


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
    ("request_body", "reason", "truth"),
    [
        (
            TaskCreate(title="Verify gold", steps=[TaskStep(id="verify", title="Verify quote")]),
            "task_steps_incomplete",
            "This task is not finished. Steps not completed yet: Verify quote.",
        ),
        (
            TaskCreate(title="Watch gold", completion_mode="continuous"),
            "task_wait_required",
            "This continuous task is not being monitored: no monitoring wait",
        ),
    ],
)
async def test_unfinished_task_gets_bounded_nudges_then_owner_attention_not_failure(
    task_db: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    request_body: TaskCreate,
    reason: str,
    truth: str,
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
    # The runtime's known truth leads; the held completion claim is only a report.
    assert question["status"] == "pending" and question["question"].startswith(truth)
    assert question["question"].endswith("Latest report: I looked at gold and it is done.")
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
    assert parameters["work_thread_id"] == run.thread_id
    async with db.sessions() as session:
        posted = await session.scalar(
            select(MessageRow).where(
                MessageRow.thread_id == run.thread_id, MessageRow.role == "assistant"
            )
        )
        assert posted and posted.content.startswith(truth)

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
    await execute_run(context, registry, 120, 2)
    run = await saved_run(context)
    assert results(run)["only"] == {"ok": True, "n": 1}
    assert turns == 2 and run.status == "completed" and run.error_code is None
    assert run.result and run.result.startswith("I stopped before finishing")
    assert run.model_metadata["exit_reason"] == "tool_round_limit"


@pytest.mark.asyncio
async def test_identical_trades_in_one_block_execute_at_most_five_times(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[str] = []

    async def trade(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
        executed.append(context.call_id)
        # A real broker result always carries a fresh operation identity.
        return {"status": "confirmed", "operation_id": "op-" + context.call_id}

    registry = ToolRegistry([Tool("fixture_trade", "Trade", Arguments, trade, financial=True)])
    # A provider that duplicates one call eight times in a single assistant block.
    block = calls(*((f"buy-{index}", "fixture_trade", 1) for index in range(8)))
    context = await conversation_run(task_db, seeded(block))
    model = Script(ModelReply(text="Five buys were confirmed; I stopped repeating it."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert executed == [f"buy-{index}" for index in range(5)]
    assert run.status == "completed" and run.error_code is None
    assert run.model_metadata["exit_reason"] == "guardrail_halt"
    observed = results(run)
    assert observed["buy-1"]["runtime_notice"][0]["kind"] == "tool_guardrail"
    blocked, halted = observed["buy-5"], observed["buy-6"]
    assert blocked["code"] == "guardrail_blocked" and blocked["executed"] is False
    assert blocked["guardrail"]["code"] == "identical_effect_block"
    assert halted["executed"] is False and halted["guardrail"]["code"] == "identical_effect_halt"
    assert observed["buy-7"]["code"] == "tool_call_not_executed"
    final_request, tools = model.requests[-1]
    assert tools == [] and "repeating tool loop" in final_request[-1].content


@pytest.mark.asyncio
async def test_an_approved_dispatch_counts_once_toward_the_effect_streak(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_agent.environment import route_key

    async def write(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        return {"version": 2}

    block = calls(("approved", "fixture_write", 1))
    # The first dispatch waited for approval; this dispatch is the execution.
    state = seeded(block) | {"waiting_call_id": "approved"}
    registry = ToolRegistry([Tool("fixture_write", "Write", Arguments, write)])
    context = await conversation_run(task_db, state)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Saved.")))
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed"
    assert run.execution_state["tool_guardrails"]["effect_streak"] == [route_key(block[0]), 1, 0]


async def task_run_with(
    fixture: Fixture, request: TaskCreate, **checkpoint: Any
) -> tuple[ToolContext, str]:
    context, task_id = await task_run(fixture, request)
    async with context.db.sessions() as session, session.begin():
        run = await session.get(RunRow, context.lease.run_id)
        assert run
        run.execution_state = {**run.execution_state, **checkpoint}
    return context, task_id


@pytest.mark.asyncio
async def test_final_task_turn_completes_when_the_last_executed_round_records_the_last_step(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_tools.tasks import tools as task_tools

    db, owner, _, _ = task_db

    async def quote(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        return {"bid": 2301.5}

    registry = ToolRegistry(
        [
            Tool("fixture_quote", "Quote", Arguments, quote, True),
            *(item for item in task_tools() if item.name == "task_step_update"),
        ]
    )
    # The final slice of the pinned Task budget: one executable round remains.
    context, task_id = await task_run_with(
        task_db,
        TaskCreate(title="Verify gold", steps=[TaskStep(id="verify", title="Verify quote")]),
        rounds=2,
        task_continuation={"version": 1, "slice": 4, "rounds_per_slice": 1},
    )
    step = ToolCall(
        id="step",
        name="task_step_update",
        arguments={
            "step_id": "verify",
            "plan_revision": 1,
            "state": "completed",
            "evidence_call_ids": ["quote"],
        },
    )
    model = Script(
        ModelReply(tool_calls=[*calls(("quote", "fixture_quote", 1)), step]),
        ModelReply(text="Verified the gold quote at 2301.5; the task is complete."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 1)
    run = await saved_run(context)
    observed = results(run)
    assert observed["quote"]["ok"] and observed["step"]["ok"]
    first, offered = model.requests[0]
    assert offered and "This is the last model round" in first[-1].content
    final, tools = model.requests[1]
    assert tools == [] and len(model.requests) == 2
    assert is_runtime_notice(final[-1]) and "tool-round limit" in final[-1].content
    # Every declared step is recorded complete with evidence: the Task completes.
    assert run.status == "completed" and run.result and run.result.startswith("Verified")
    assert run.model_metadata["exit_reason"] == "tool_round_limit"
    async with db.sessions() as session:
        task = await get_task(session, owner, task_id)
        assert task.state["task"]["status"] == "completed"


async def held_for_attention(task_db: Fixture, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    context, task_id = await task_run(
        task_db,
        TaskCreate(title="Verify gold", steps=[TaskStep(id="verify", title="Verify quote")]),
    )
    monkeypatch.setattr(
        "lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Gold looks fine."))
    )
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "waiting_input"
    return run.id, task_id


async def reclaim(task_db: Fixture, run_id: str, worker: str) -> ToolContext:
    db, _, _, _ = task_db
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, worker, 120, "work")
        assert claimed and claimed.id == run_id
        claimed.status = "running"
        lease = Lease(run_id=claimed.id, owner=worker, fence=claimed.lease_fence)
        thread = claimed.thread_id
    return context_for(task_db, lease, thread)


@pytest.mark.asyncio
async def test_owner_attention_task_resumes_and_revises_through_task_controls(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_contracts.tasks import TaskControl
    from lonora_db.agent_state import agent_live_state
    from lonora_db.tasks import control_task

    db, owner, agent, _ = task_db
    run_id, task_id = await held_for_attention(task_db, monkeypatch)
    async with db.sessions() as session:
        task = await get_task(session, owner, task_id)
        projected = await snapshot(session, task)
        assert projected["can_resume"] is True and projected["waiting_reason"] == "owner_attention"
        live = await agent_live_state(session, owner, agent)
        assert (live.state, live.reason_code) == ("action_required", "task_attention_required")

    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task_id, action="resume", expected_version=task.version),
        )
    async with db.sessions() as session:
        run = await session.get(RunRow, run_id)
        task = await get_task(session, owner, task_id)
        assert run and run.status == "queued"
        assert "pending_input_request" not in run.execution_state
        assert run.execution_state["input_requests"][-1]["status"] == "cancelled"
        assert task.state["task"]["status"] == "queued"
        assert task.state["task"]["waiting_reason"] is None

    # The resumed Run continues its checkpoint with a new review epoch.
    resumed = Script(ModelReply(text="Still checking gold."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", resumed)
    await execute_run(await reclaim(task_db, run_id, "resume-writer"), ToolRegistry([]), 120, 8)
    first, _ = resumed.requests[0]
    assert is_runtime_notice(first[-1]) and "owner_resumed" in first[-1].content
    # Fresh nudges: two completion checks before the owner is asked again.
    assert len(resumed.requests) == 3
    async with db.sessions() as session:
        run = await session.get(RunRow, run_id)
        task = await get_task(session, owner, task_id)
        assert run and run.status == "waiting_input"
        assert "owner_attention_resumed" not in run.execution_state
        assert task.state["task"]["waiting_reason"] == "owner_attention"

    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(
                task_id=task_id,
                action="revise",
                expected_version=task.version,
                instruction="Use the spot quote only.",
            ),
        )
    async with db.sessions() as session:
        run = await session.get(RunRow, run_id)
        task = await get_task(session, owner, task_id)
        assert run and run.status == "queued" and task.state["task"]["status"] == "queued"
        assert task.state["task"]["plan_revision"] == 2
    revised = Script(ModelReply(text="Checking the spot quote."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", revised)
    await execute_run(await reclaim(task_db, run_id, "revise-writer"), ToolRegistry([]), 120, 8)
    first, _ = revised.requests[0]
    assert any("<task_plan_revision>" in item.content for item in first)
    assert any(is_runtime_notice(item) and "revised it" in item.content for item in first)


@pytest.mark.asyncio
async def test_a_second_outage_after_resume_asks_the_owner_again_with_a_new_question(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_agent import tool_loop
    from lonora_agent.model_recovery import BackoffProfile
    from lonora_contracts.tasks import TaskControl
    from lonora_core.user_error import LonoraError
    from lonora_db.tasks import control_task

    class Down:
        async def __call__(self, *_: Any, **__: Any) -> Any:
            raise LonoraError("model_provider_unavailable", 502)

    db, owner, _, _ = task_db
    # Escalate on the first transient failure; the WORK profile does so after six.
    monkeypatch.setattr(tool_loop, "WORK", BackoffProfile(30.0, 900.0, 1))
    context, task_id = await task_run(
        task_db, TaskCreate(title="Verify gold", steps=[TaskStep(id="v", title="Verify quote")])
    )
    call = ToolCall(id="q1", name="fixture_quote", arguments={})
    # The transcript ends with a tool result, so the resume notice joins that
    # result and the message count does not change between the two escalations.
    messages = [
        ModelMessage(role="user", content="Verify gold"),
        ModelMessage(role="assistant", content="", tool_calls=[call]),
        ModelMessage(role="tool", tool_call_id="q1", content='{"ok": true, "bid": 2301.5}'),
    ]
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, context.lease.run_id)
        assert run
        run.execution_state = {
            **run.execution_state,
            "messages": [item.model_dump(mode="json") for item in messages],
            "rounds": 1,
            "task_plan_revision": 1,
        }
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Down())
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "waiting_input", (run.status, run.error_code)
    first = run.execution_state["pending_input_request"]["id"]
    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task_id, action="resume", expected_version=task.version),
        )
    # The provider is still down when the resumed Run is claimed.
    await execute_run(await reclaim(task_db, run.id, "resume-writer"), ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "waiting_input", (run.status, run.error_code)
    second = run.execution_state["pending_input_request"]["id"]
    assert second != first
    assert [(item["id"], item["status"]) for item in run.execution_state["input_requests"]] == [
        (first, "cancelled"),
        (second, "pending"),
    ]
