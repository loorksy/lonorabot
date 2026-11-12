"""The offer record and its obligation (phase 3c).

A question's choice can be bound to the exact calls it stands for, and the owner's pick
makes those calls an obligation of the Run it resumes. Pure cases on a built transcript
and the shipped tool catalogue, the binding check against a real Run, and the whole path
in the loop: ask, pick, the check, the calls.
"""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.history import history_context
from lonora_agent.conversation_gate import choice_left_undone, conversation_stop_gate
from lonora_agent.executor import execute_run
from lonora_agent.loop_outcomes import closing_lines
from lonora_agent.offers import (
    CHOICE_LINE_AR,
    CHOICE_LINE_EN,
    PICKED,
    bind_choices,
    merge_answer,
)
from lonora_agent.runtime_notices import is_owner_message, is_runtime_notice, notice_message
from lonora_agent.stop_gates import CONVERSATION_KEY
from lonora_contracts.domain import InputAnswer, MessageCreate
from lonora_contracts.runs import Lease
from lonora_core.user_error import ToolRefusal
from lonora_db.messages import send_message
from lonora_db.runs import OFFER_OBLIGATION, claim_next, run_data
from lonora_db.schema import MessageRow, RunRow
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.provenance import mark_external_content
from lonora_tools.registry import ToolRegistry
from lonora_tools.runtime_control import tools as runtime_tools
from pydantic import BaseModel
from sqlalchemy import func, select
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import (
    Fixture,
    Script,
    context_for,
    conversation_run,
    saved_run,
)

REGISTRY = load_tools()
PERMITTED = REGISTRY.names("full")
ASKED = ModelMessage(role="user", content="نظّف التنبيهات القديمة")
PICK = ModelMessage(role="user", content="احذف الكل")
# What the Run is told after the pick; the check reads the transcript from here on.
TOLD = notice_message(PICKED, "The owner picked choice all of your question.")
REPLY = ModelMessage(role="assistant", content="تم حذف التنبيهات.")
# Another agent's outcome reaches a Run as a user-role message of the conversation.
PEER = ModelMessage(
    role="user", content='<peer_outcome agent="Scout">Gold is quiet.</peer_outcome>'
)
DONE = {"ok": True, "cancelled": True}
REFUSED = {
    "ok": False,
    "code": "watch_not_owned",
    "class": "permission",
    "retryable": False,
    "recovery": {"category": "permission_denied", "next_action": "tell_owner"},
}
MISSING: dict[str, Any] = {
    "ok": False,
    "code": "watch_not_found",
    "class": "resolution",
    "retryable": False,
    "candidates": [],
}


def picked(*tools: str) -> dict[str, Any]:
    """A Run the owner's pick resumed: the choice was bound to one call per name."""
    return {
        "owner_started": True,
        "owner_request_start": 0,
        OFFER_OBLIGATION: {
            "question_id": "ask",
            "choice_id": "all",
            "answer_message_id": "m-pick",
            "actions": [
                {"tool": tool, "arguments": {"watch_id": f"w{index}"}}
                for index, tool in enumerate(tools)
            ],
            "status": "open",
        },
    }


def exchange(tool: str, result: dict[str, Any], key: str = "a", **arguments: Any) -> list[Any]:
    call = ToolCall(id=f"c-{tool}-{key}", name=tool, arguments=arguments)
    return [
        ModelMessage(role="assistant", content="", tool_calls=[call]),
        ModelMessage(role="tool", tool_call_id=call.id, content=json.dumps(result)),
    ]


def gate(state: dict[str, Any], *messages: ModelMessage) -> Any:
    return conversation_stop_gate(state, list(messages), REGISTRY, PERMITTED)


def test_a_reply_with_no_call_after_the_pick_continues_once_and_names_what_is_left():
    state = picked("watch_cancel")
    transcript = [ASKED, PICK, TOLD, REPLY]
    verdict = gate(state, *transcript)
    assert verdict.continue_turn
    assert "picked choice all" in verdict.nudge and "still to make: watch_cancel." in verdict.nudge
    assert verdict.nudge.startswith("Automated runtime check. This is not a message from the owner")
    assert state[CONVERSATION_KEY]["fired"] == [
        {"condition": "choice_not_carried_out", "tool": "watch_cancel", "call_id": "ask"}
    ]
    # One fact is raised once: a reply that still leaves it undone stands.
    again = [*transcript, notice_message("conversation_check", verdict.nudge), REPLY]
    assert not gate(state, *again).continue_turn
    assert state[CONVERSATION_KEY]["attempts"] == 1


def test_a_successful_call_of_the_bound_tool_settles_it_whatever_its_arguments():
    # The model named the watch another way: the tool succeeded, so nothing is asked again.
    state = picked("watch_cancel")
    made = exchange("watch_cancel", DONE, watch_id="ذهب فوق 2400")
    transcript = [ASKED, PICK, TOLD, *made, REPLY]
    assert not gate(state, *transcript).continue_turn
    assert not choice_left_undone(state, transcript, REGISTRY)
    assert state[OFFER_OBLIGATION]["outcome"] == "met"
    assert state[OFFER_OBLIGATION]["status"] == "open"
    assert CONVERSATION_KEY not in state


def test_another_agents_outcome_after_the_calls_never_asks_for_them_again():
    # The outcome is merged after the change was made: the calls are still read from the
    # pick on, so nothing is repeated and no line is added.
    state = picked("watch_cancel")
    made = exchange("watch_cancel", DONE, watch_id="w0")
    transcript = [ASKED, PICK, TOLD, *made, PEER, REPLY]
    assert not gate(state, *transcript).continue_turn
    assert closing_lines(state, transcript, REPLY.content, REGISTRY) == REPLY.content
    assert state[OFFER_OBLIGATION]["outcome"] == "met"
    # With nothing made, the same outcome does not hide what is still to do.
    waiting = picked("watch_cancel")
    assert gate(waiting, ASKED, PICK, TOLD, PEER, REPLY).continue_turn
    # Without the pick's notice there is no pick to read from: nothing is checked.
    assert not gate(picked("watch_cancel"), ASKED, PICK, REPLY).continue_turn
    assert not choice_left_undone(picked("watch_cancel"), [ASKED, PICK, REPLY], REGISTRY)


def test_every_bound_call_is_counted():
    state = picked("watch_cancel", "watch_cancel", "watch_cancel")
    transcript = [ASKED, PICK, TOLD, *exchange("watch_cancel", DONE, watch_id="w0"), REPLY]
    verdict = gate(state, *transcript)
    assert verdict.continue_turn
    assert "1 of them succeeded" in verdict.nudge and "watch_cancel (2 calls)" in verdict.nudge
    rest = [
        *transcript[:-1],
        *exchange("watch_cancel", DONE, "b", watch_id="w1"),
        *exchange("watch_cancel", DONE, "c", watch_id="w2"),
        REPLY,
    ]
    assert not gate(picked("watch_cancel", "watch_cancel", "watch_cancel"), *rest).continue_turn


def test_a_call_whose_outcome_is_not_known_is_never_asked_for_again():
    interrupted = {"ok": False, "code": "tool_execution_uncertain"}
    state = picked("routine_create")
    transcript = [ASKED, PICK, TOLD, *exchange("routine_create", interrupted, title="x"), REPLY]
    assert not gate(state, *transcript).continue_turn
    assert not choice_left_undone(state, transcript, REGISTRY)


def test_a_call_that_failed_leaves_the_choice_to_carry_out():
    state = picked("watch_cancel")
    transcript = [ASKED, PICK, TOLD, *exchange("watch_cancel", MISSING, watch_id="w9"), REPLY]
    verdict = gate(state, *transcript)
    assert verdict.continue_turn and "0 of them succeeded" in verdict.nudge


@pytest.mark.parametrize(
    "held",
    [
        exchange("watch_cancel", REFUSED, watch_id="w0"),
        exchange("trade_execute", {"ok": True, "status": "filled"}, symbol="XAUUSDm"),
    ],
)
def test_a_rule_or_a_trade_in_the_request_holds_the_reply(held: list[ModelMessage]):
    state = picked("watch_cancel")
    transcript = [ASKED, PICK, TOLD, *held, REPLY]
    assert not gate(state, *transcript).continue_turn
    # Nothing is appended either: the reply is the model's account of the refusal.
    assert closing_lines(state, transcript, REPLY.content, REGISTRY) == REPLY.content
    assert state[OFFER_OBLIGATION]["outcome"] == "held"


def test_the_reply_that_leaves_the_choice_undone_gets_one_line():
    state = picked("watch_cancel")
    transcript = [ASKED, PICK, TOLD, REPLY]
    text = closing_lines(state, transcript, REPLY.content, REGISTRY)
    assert text == REPLY.content + "\n\n" + CHOICE_LINE_AR
    assert transcript[-1].content == text and state[OFFER_OBLIGATION]["outcome"] == "unmet"
    # A second pass over the same reply adds nothing.
    assert closing_lines(state, transcript, text, REGISTRY) == text
    # A reply drafted again is judged afresh: the line is owed until the calls are made.
    again = [*transcript[:-1], ModelMessage(role="assistant", content="كل شيء جاهز.")]
    assert closing_lines(state, again, "كل شيء جاهز.", REGISTRY).endswith(CHOICE_LINE_AR)
    english = [
        ModelMessage(role="user", content="Clean up the old alerts please"),
        ModelMessage(role="user", content="Delete all of them"),
        TOLD,
        ModelMessage(role="assistant", content="Deleted."),
    ]
    assert closing_lines(picked("watch_cancel"), english, "Deleted.", REGISTRY).endswith(
        CHOICE_LINE_EN
    )


def test_the_pick_is_followed_by_what_it_was_bound_to():
    state = picked("watch_cancel", "watch_pause")
    messages = [ASKED, PICK]
    merge_answer(state, messages, "m-pick", owner=True)
    notice = messages[-1]
    assert is_runtime_notice(notice) and not is_owner_message(notice)
    assert 'watch_cancel {\\"watch_id\\": \\"w0\\"}' in notice.content
    assert "watch_pause" in notice.content and "picked choice all" in notice.content
    assert state[OFFER_OBLIGATION]["status"] == "open"
    # Still the pick's request: the check reads from the pick on.
    assert gate(state, *messages, REPLY).continue_turn


def test_a_later_message_of_the_owner_closes_the_offer_unchecked():
    # The owner picked, the calls were made, then the owner wrote again: nothing is
    # asked for a second time and nothing is appended.
    state = picked("watch_cancel")
    messages = [ASKED, PICK, TOLD, *exchange("watch_cancel", DONE, watch_id="w0"), REPLY]
    later = ModelMessage(role="user", content="استنى")
    messages.append(later)
    merge_answer(state, messages, "m-later", owner=True)
    assert state[OFFER_OBLIGATION]["status"] == "superseded"
    transcript = [*messages, ModelMessage(role="assistant", content="حاضر.")]
    assert not gate(state, *transcript).continue_turn
    assert closing_lines(state, transcript, "حاضر.", REGISTRY) == "حاضر."
    # The same holds when the calls were never made: the owner moved on.
    undone = picked("watch_cancel")
    merge_answer(undone, [ASKED, PICK, TOLD, later], "m-later", owner=True)
    after = [ASKED, PICK, TOLD, later, ModelMessage(role="assistant", content="حاضر.")]
    assert not gate(undone, *after).continue_turn
    assert closing_lines(undone, after, "حاضر.", REGISTRY) == "حاضر."
    # Another agent's message is not the owner's: the offer stays open.
    peer = picked("watch_cancel")
    merge_answer(peer, [ASKED, PICK, TOLD], "m-peer", owner=False)
    assert peer[OFFER_OBLIGATION]["status"] == "open"


def test_a_task_or_a_wake_is_never_checked():
    task = {**picked("watch_cancel"), "owner_started": False}
    assert not gate(task, ASKED, PICK, TOLD, REPLY).continue_turn
    assert not choice_left_undone(task, [ASKED, PICK, TOLD, REPLY], REGISTRY)
    wake = ModelMessage(role="user", content="<runtime_wake>{}</runtime_wake>")
    assert not gate(picked("watch_cancel"), ASKED, PICK, TOLD, wake, REPLY).continue_turn
    assert not choice_left_undone(
        picked("watch_cancel"), [ASKED, PICK, TOLD, wake, REPLY], REGISTRY
    )


class Arguments(BaseModel):
    n: int = 0


async def _done(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"cancelled": arguments["n"]}


def offer_registry() -> ToolRegistry:
    wait = next(tool for tool in runtime_tools() if tool.name == "wait_for_input")
    return ToolRegistry(
        [
            wait,
            Tool("fixture_cancel", "Cancel", Arguments, _done),
            Tool("fixture_read", "Read", Arguments, _done, True),
            Tool("fixture_trade", "Trade", Arguments, _done, financial=True),
        ]
    )


def choices(*actions: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": "all", "label": "Delete both", "actions": list(actions)},
        {"id": "keep", "label": "Keep them"},
    ]


def bound(tool: str, **arguments: Any) -> dict[str, Any]:
    return {"tool": tool, "arguments": arguments}


@pytest.mark.asyncio
async def test_only_a_real_action_of_this_run_can_be_bound(task_db: Fixture) -> None:
    registry = offer_registry()
    context = await conversation_run(task_db)
    effects = await bind_choices(
        context,
        registry,
        "full",
        choices(bound("fixture_cancel", n=1), bound("fixture_cancel", n=2), bound("fixture_read")),
    )
    assert effects == {
        "all": [
            {"name": "fixture_cancel", "toolset": "", "effect": "change", "count": 2},
            {"name": "fixture_read", "toolset": "", "effect": "read", "count": 1},
        ]
    }
    # A question that binds nothing is asked as before.
    assert await bind_choices(context, registry, "full", choices()) == {}
    for action, why in [
        (bound("no_such_tool"), "not a tool of this turn"),
        (bound("fixture_trade", n=1), "moves money"),
        (bound("wait_for_input", question="?"), "not something a choice can stand for"),
        (bound("tool_call", name="fixture_cancel"), "not something a choice can stand for"),
        (bound("fixture_cancel", n="many"), "would not accept these arguments"),
        (bound("fixture_cancel", n=1, note="x" * 5000), "too long"),
    ]:
        with pytest.raises(ToolRefusal) as refused:
            await bind_choices(context, registry, "full", choices(action))
        details = refused.value.details
        assert refused.value.code == "offer_action_invalid" and details["class"] == "input"
        assert "Choice all binds " + action["tool"] in details["hint"] and why in details["hint"]
    # A helper may read, so it cannot bind a change it could not make itself.
    with pytest.raises(ToolRefusal) as refused:
        await bind_choices(context, registry, "helper", choices(bound("fixture_cancel", n=1)))
    assert "not a tool of this turn" in refused.value.details["hint"]


@pytest.mark.asyncio
async def test_nothing_is_bound_once_the_run_read_what_others_wrote(task_db: Fixture) -> None:
    db = task_db[0]
    registry = offer_registry()
    asked = choices(bound("fixture_cancel", n=1))
    context = await conversation_run(task_db)

    async def started_by(trigger: str) -> None:
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.trigger = trigger

    # A wake is not the owner's request, whatever it read.
    await started_by("watch")
    with pytest.raises(ToolRefusal) as refused:
        await bind_choices(context, registry, "full", asked)
    assert refused.value.code == "offer_action_unavailable"
    await started_by("user")
    assert await bind_choices(context, registry, "full", asked)
    async with db.sessions() as session, session.begin():
        await mark_external_content(session, context.lease.run_id, "web_search")
    with pytest.raises(ToolRefusal) as refused:
        await bind_choices(context, registry, "full", asked)
    assert refused.value.code == "offer_action_unavailable"
    assert "Ask the same question without actions" in refused.value.details["hint"]


async def _no_skill_refresh(*_: Any, **__: Any) -> None:
    return None


@pytest.fixture(autouse=True)
def _fixture_registry_has_no_skills(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lonora_agent.tool_loop.refresh_skill_context", _no_skill_refresh)


def ask(*actions: dict[str, Any], call: str = "ask") -> ModelReply:
    return ModelReply(
        text="",
        tool_calls=[
            ToolCall(
                id=call,
                name="wait_for_input",
                arguments={"question": "Delete the two old alerts?", "choices": choices(*actions)},
            )
        ],
    )


async def answer(
    fixture: Fixture, run_id: str, text: str, choice: str | None, nonce: str = ""
) -> ToolContext:
    """The owner's answer, then the same Run claimed again."""
    db, owner, _, thread = fixture
    async with db.sessions() as session, session.begin():
        sent = await send_message(session, owner, thread, answered(run_id, text, choice, nonce))
        assert sent["run_ids"] == [run_id]
        run = await claim_next(session, "loop-writer", 120, "conversation")
        assert run and run.id == run_id
        run.status = "running"
        lease = Lease(run_id=run.id, owner="loop-writer", fence=run.lease_fence)
    return context_for(fixture, lease, thread)


def answered(run_id: str, text: str, choice: str | None, nonce: str = "") -> MessageCreate:
    pick = InputAnswer(run_id=run_id, question_id="ask", choice_id=choice) if choice else None
    message = MessageCreate(content=text, input_answer=pick)
    return message.model_copy(update={"client_nonce": nonce}) if nonce else message


def cancels(*numbers: int) -> ModelReply:
    return ModelReply(
        text="",
        tool_calls=[
            ToolCall(id=f"x{n}", name="fixture_cancel", arguments={"n": n}) for n in numbers
        ],
    )


@pytest.mark.asyncio
async def test_a_picked_choice_is_carried_out_before_the_turn_ends(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = offer_registry()
    model = Script(
        ask(bound("fixture_cancel", n=1), bound("fixture_cancel", n=2)),
        ModelReply(text="Done."),
        cancels(1, 2),
        ModelReply(text="Both alerts are deleted."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "waiting_input" and OFFER_OBLIGATION not in run.execution_state
    # The card is told what a pick does, never the calls themselves.
    assert run_data(run)["input_request"]["choices"] == [
        {
            "id": "all",
            "label": "Delete both",
            "effects": [{"name": "fixture_cancel", "toolset": "", "effect": "change", "count": 2}],
        },
        {"id": "keep", "label": "Keep them"},
    ]

    context = await answer(task_db, run.id, "Delete both", "all")
    assert (await saved_run(context)).execution_state[OFFER_OBLIGATION]["actions"] == [
        bound("fixture_cancel", n=1),
        bound("fixture_cancel", n=2),
    ]
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Both alerts are deleted."
    assert len(model.requests) == 4
    after_pick, _ = model.requests[1]
    assert after_pick[-2].content == "Delete both" and is_owner_message(after_pick[-2])
    assert is_runtime_notice(after_pick[-1]) and "choice_picked" in after_pick[-1].content
    checked, _ = model.requests[2]
    assert "conversation_check" in checked[-1].content
    assert "fixture_cancel (2 calls)" in checked[-1].content
    assert run.execution_state[OFFER_OBLIGATION]["outcome"] == "met"
    assert run.execution_state[CONVERSATION_KEY]["fired"] == [
        {"condition": "choice_not_carried_out", "tool": "fixture_cancel", "call_id": "ask"}
    ]


@pytest.mark.asyncio
async def test_a_reply_that_leaves_the_pick_undone_says_so_once(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = offer_registry()
    model = Script(ask(bound("fixture_cancel", n=1)), ModelReply(text="Done."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, registry, 120, 8)
    context = await answer(task_db, context.lease.run_id, "Delete both", "all")
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    # Asked once, then the reply stands with the one true line; never a loop.
    assert run.status == "completed" and run.result == "Done.\n\n" + CHOICE_LINE_EN
    assert len(model.requests) == 3
    assert run.execution_state[OFFER_OBLIGATION]["outcome"] == "unmet"


@pytest.mark.asyncio
async def test_an_answer_that_is_not_a_bound_pick_leaves_nothing_to_check(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = offer_registry()
    for text, choice in [("Only the first one", None), ("Keep them", "keep")]:
        model = Script(ask(bound("fixture_cancel", n=1)), ModelReply(text="Understood."))
        monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
        context = await conversation_run(task_db)
        await execute_run(context, registry, 120, 8)
        # An obligation left on the Run by an earlier pick is cleared by any other answer.
        async with task_db[0].sessions() as session, session.begin():
            waiting = await session.get(RunRow, context.lease.run_id)
            assert waiting
            waiting.execution_state = {
                **waiting.execution_state,
                OFFER_OBLIGATION: picked("fixture_cancel")[OFFER_OBLIGATION],
            }
        context = await answer(task_db, context.lease.run_id, text, choice)
        assert OFFER_OBLIGATION not in (await saved_run(context)).execution_state
        await execute_run(context, registry, 120, 8)
        run = await saved_run(context)
        assert run.status == "completed" and run.result == "Understood."
        assert len(model.requests) == 2 and CONVERSATION_KEY not in run.execution_state


def reads(number: int) -> ModelReply:
    call = ToolCall(id=f"r{number}", name="fixture_read", arguments={"n": number})
    return ModelReply(text="", tool_calls=[call])


@pytest.mark.asyncio
async def test_the_limit_report_says_the_pick_was_left_undone(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = offer_registry()
    model = Script(
        ask(bound("fixture_cancel", n=1)), reads(1), reads(2), ModelReply(text="I ran out of time.")
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, registry, 120, 4)
    context = await answer(task_db, context.lease.run_id, "Delete both", "all")
    # Two rounds are left after the question: both go to reads, and the report ends the turn.
    await execute_run(context, registry, 120, 4)
    run = await saved_run(context)
    assert run.status == "completed" and run.execution_state["exit_reason"] == "tool_round_limit"
    assert len(model.requests) == 4
    assert run.result == "I ran out of time.\n\n" + CHOICE_LINE_EN
    assert run.execution_state[OFFER_OBLIGATION]["outcome"] == "unmet"


@pytest.mark.asyncio
async def test_a_pick_binds_nothing_more_and_later_turns_never_read_the_bound_calls(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    registry = offer_registry()
    model = Script(
        ask(bound("fixture_cancel", n=1)),
        ask(bound("fixture_cancel", n=2), call="again"),
        cancels(1),
        ModelReply(text="Deleted."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    context = await conversation_run(task_db)
    await execute_run(context, registry, 120, 8)
    run_id = context.lease.run_id
    context = await answer(task_db, run_id, "Delete both", "all", "pick-1")
    # The same answer delivered twice is one answer.
    before = (await saved_run(context)).execution_state[OFFER_OBLIGATION]
    async with db.sessions() as session, session.begin():
        again = await send_message(
            session, owner, thread, answered(run_id, "Delete both", "all", "pick-1")
        )
    assert again["deduplicated"] is True
    assert (await saved_run(context)).execution_state[OFFER_OBLIGATION] == before
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Deleted."
    # A pick is a tap on a label, not the owner's typed words: the Run it resumed asked a
    # second bound question, which was refused and never published.
    refused = next(
        json.loads(item["content"])
        for item in run.execution_state["messages"]
        if item["role"] == "tool" and item.get("tool_call_id") == "again"
    )
    assert refused["ok"] is False and refused["code"] == "offer_action_unavailable"
    assert [item["id"] for item in run.execution_state["input_requests"]] == ["ask"]
    # A later turn reads the question with its labels, never the calls behind them.
    async with db.sessions() as session:
        last = await session.scalar(
            select(func.max(MessageRow.seq)).where(MessageRow.thread_id == thread)
        )
        restored = await history_context(session, thread, int(last or 0), agent_id=agent)
    text = "\n".join(message.content for message in restored)
    assert (
        '<question_choices>[{"id": "all", "label": "Delete both"}, '
        '{"id": "keep", "label": "Keep them"}]</question_choices>' in text
    )
    assert "fixture_cancel" not in text and "actions" not in text
