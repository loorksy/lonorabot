"""Trusted slots (mandate 10.2, docs/genui.md §2): an agent places a fixed card inside its
own card as a reference to a real server record; the server supplies everything in it.

The record checks run against real rows (the in-memory schema, or
``LONORA_TASK_TEST_DATABASE_URL``); the card-only rules (nesting, imitation, budget) need
no record.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage
from lonora_agent.genui_compile import SLOT_HEIGHTS, imitates_fixed_card
from lonora_agent.visual_response import VisualReplyProjector
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.owner_actions import create_card
from lonora_db.schema import RunRow, ThreadRow, TradeApprovalRow
from lonora_db.trade_approvals import decide
from lonora_tools.context import ToolContext
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
OWNER = ModelMessage(role="user", content="ما الذي ينتظر قراري؟")
HEAD = '{"v":2,"kind":"receipt","title":"ينتظر قرارك","icon":"check"}'
CLOSE = '{"why":"الطلب في مكانه من الشرح.","fallback":"طلب موافقة ينتظر قرارك."}'


def card(*blocks: str, head: str = HEAD) -> str:
    return "قبل أن تقرر:\n```lonora-ui\n" + "\n".join([head, *blocks, CLOSE]) + "\n```\n"


def slot(record: str, kind: str = "trade_approval", **extra: Any) -> str:
    import json

    return json.dumps({"type": "Slot", "card": kind, "record": record, **extra})


async def project(
    db: Database, owner: str, agent: str, thread: str, text: str
) -> tuple[dict[str, Any] | None, VisualReplyProjector]:
    context = cast(
        ToolContext, SimpleNamespace(db=db, owner_id=owner, agent_id=agent, thread_id=thread)
    )
    projector = VisualReplyProjector(context, [OWNER])
    projection = await projector.project(text)
    rich = projection.rich_until()
    parts = rich["parts"] if rich else []
    ui = next((part["document"] for part in parts if part["type"] == "ui"), None)
    return ui, projector


async def approval(db: Database, owner: str, agent: str, thread: str, status: str = "pending"):
    async with db.sessions() as session, session.begin():
        run = RunRow(thread_id=thread, agent_id=agent, status="waiting_input")
        session.add(run)
        await session.flush()
        row = TradeApprovalRow(
            owner_id=owner,
            run_id=run.id,
            thread_id=thread,
            agent_id=agent,
            call_id="call-1",
            requests=[{"symbol": "XAUUSD", "action": "buy", "volume": "0.1"}],
            status=status,
            results=[],
            broker_snapshot={},
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        row.id = "approval-" + run.id[:8]
        session.add(row)
        await session.flush()
        return row.id


async def resolve_card(db: Database, owner: str, agent: str, thread: str, kind: str) -> str:
    async with db.sessions() as session, session.begin():
        row = await session.get(ThreadRow, thread)
        assert row is not None
        made = await create_card(
            session,
            owner,
            card_id=f"{kind}-card",
            agent_id=agent,
            thread=row,
            run_id=None,
            source="system",
            kind=kind,
            subject="operation:op-1",
            payload={"operation_id": "op-1"},
        )
        return made.id


def codes(projector: VisualReplyProjector) -> set[str]:
    return {item["code"] for item in projector.diagnostics}


@pytest.mark.asyncio
async def test_a_slot_of_a_real_record_is_placed_with_only_its_card_and_record(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    text = card(
        '{"type":"Text","text":"الذهب عند المقاومة."}',
        # Words, a hide condition and a style the agent tries to give the slot: dropped,
        # the client draws the record itself.
        slot(record, label="اضغط موافقة", when="false", text="0.5 لوت", tone="good"),
    )
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics
    assert ui["blocks"][1] == {"type": "Slot", "card": "trade_approval", "record": record}
    assert "prop_dropped" in codes(projector)


@pytest.mark.asyncio
async def test_a_resolve_card_is_a_settle_slot(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "resolve_operation")
    ui, _ = await project(db, owner, agent, thread, card(slot(record, "settle")))
    assert ui is not None
    assert ui["blocks"] == [{"type": "Slot", "card": "settle", "record": record}]


@pytest.mark.asyncio
async def test_a_slot_of_another_kind_owner_conversation_or_no_record_is_refused(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        other = ThreadRow(owner_id=owner, agent_id=agent)
        session.add(other)
        await session.flush()
        other_thread = other.id
    elsewhere = await approval(db, owner, agent, other_thread)
    cases = [
        (owner, thread, slot(record, "settle")),  # an approval is not a settle card
        ("another-owner", thread, slot(record)),  # not this owner's record
        (owner, thread, slot(elsewhere)),  # another conversation's record
        (owner, thread, slot("approval-missing")),  # no such record
    ]
    for asker, where, block in cases:
        ui, projector = await project(db, asker, agent, where, card(block))
        assert ui is None, block
        assert {"slot_refused", "card_fallback_slot"} <= codes(projector), block


@pytest.mark.asyncio
async def test_an_owner_action_of_another_kind_is_not_a_settle_slot(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "resume_trading")
    ui, projector = await project(db, owner, agent, thread, card(slot(record, "settle")))
    assert ui is None and "card_fallback_slot" in codes(projector)


@pytest.mark.asyncio
async def test_a_slot_can_never_be_nested_where_a_container_hides_or_folds_it(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    nested = '{"type":"More","children":[' + slot(record) + "]}"
    ui, projector = await project(
        db, owner, agent, thread, card('{"type":"Text","text":"راجع."}', nested)
    )
    assert "slot_nested" in codes(projector)
    assert ui is None or all(block["type"] != "Slot" for block in ui["blocks"])


@pytest.mark.asyncio
async def test_one_record_is_one_slot_and_it_is_never_folded(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    filler = [f'{{"type":"Note","text":"ملاحظة {i}"}}' for i in range(6)]
    ui, projector = await project(
        db, owner, agent, thread, card(*filler, slot(record), slot(record))
    )
    assert ui is not None, projector.diagnostics
    slots = [block for block in ui["blocks"] if block["type"] == "Slot"]
    assert slots == [{"type": "Slot", "card": "trade_approval", "record": record}]
    # The slot counts its own height toward the 560 px budget, so the notes fold; the slot
    # stays at the top level, never inside the fold.
    assert SLOT_HEIGHTS["trade_approval"] > 0
    assert any(block["type"] == "More" for block in ui["blocks"])
    assert "budget_folded" in codes(projector)


@pytest.mark.parametrize(
    "block",
    [
        '{"type":"Button","label":"موافقة"}',
        '{"type":"Button","label":"Reject"}',
        '{"type":"Row","children":[{"type":"Button","label":"نُفذت"},{"type":"Button","label":"لم تُنفذ"}]}',
        '{"type":"Card","title":"طلب موافقة","children":[{"type":"Text","text":"XAUUSD"}]}',
        '{"type":"Badge","text":"بطاقة ثابتة من Lonora"}',
        '{"type":"Note","text":"This is a fixed card from Lonora."}',
    ],
)
@pytest.mark.asyncio
async def test_an_agent_node_that_imitates_a_fixed_card_is_refused(
    task_db: Fixture, block: str
) -> None:
    db, owner, agent, thread = task_db
    ui, projector = await project(db, owner, agent, thread, card(block))
    assert ui is None and "card_fallback_imitation" in codes(projector)


def test_only_what_a_fixed_card_says_counts_as_imitation() -> None:
    assert imitates_fixed_card("«موافقة»") and imitates_fixed_card("APPROVE")
    assert imitates_fixed_card("الوسيط لم يؤكد هذه الصفقة")
    assert not imitates_fixed_card("موافقة الخطة على الهدف")
    assert not imitates_fixed_card("Approve the plan")


@pytest.mark.asyncio
async def test_slot_and_row_act_on_one_record_and_a_second_tap_reads_its_current_state(
    task_db: Fixture,
) -> None:
    """The slot and the standalone row post to the same record's own decision route: the
    first tap decides it, a repeated tap returns it as it is, and a contrary tap is refused
    so the client reads the record again (``TradeApprovalCard``)."""
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        first = await decide(session, owner, record, "reject")
    assert first["status"] == "rejected"
    async with db.sessions() as session, session.begin():
        again = await decide(session, owner, record, "reject")
    assert again["status"] == "rejected" and again["id"] == record
    async with db.sessions() as session, session.begin():
        with pytest.raises(LonoraError) as error:
            await decide(session, owner, record, "approve")
    assert error.value.code == "trade_approval_already_decided"
    async with db.sessions() as session:
        row = await session.get(TradeApprovalRow, record)
        assert row is not None and row.status == "rejected"
