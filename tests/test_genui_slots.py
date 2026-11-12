"""Trusted slots (mandate 10.2, docs/genui.md §4a): an agent places a fixed card inside its
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
    db: Database, owner: str, agent: str, thread: str, text: str, run: str | None = None
) -> tuple[dict[str, Any] | None, VisualReplyProjector]:
    context = cast(
        ToolContext,
        SimpleNamespace(
            db=db,
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            lease=SimpleNamespace(run_id=run),
        ),
    )
    projector = VisualReplyProjector(context, [OWNER])
    projection = await projector.project(text)
    rich = projection.rich_until()
    parts = cast(list[dict[str, Any]], rich["parts"] if rich else [])
    ui = next((cast(dict[str, Any], p["document"]) for p in parts if p["type"] == "ui"), None)
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
async def test_a_run_working_in_its_own_thread_places_slots_of_its_origin_conversation(
    task_db: Fixture,
) -> None:
    """A broker-event or watch Run works in a work thread; its reply, approvals and cards
    land in its origin conversation, where its slots' records are."""
    db, owner, agent, thread = task_db
    record = await approval(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        work = ThreadRow(owner_id=owner, agent_id=agent)
        session.add(work)
        await session.flush()
        run = RunRow(
            thread_id=work.id,
            agent_id=agent,
            status="running",
            model_metadata={"origin_thread_id": thread},
        )
        session.add(run)
        await session.flush()
        work_thread, run_id = work.id, run.id
    ui, projector = await project(db, owner, agent, work_thread, card(slot(record)), run_id)
    assert ui is not None, projector.diagnostics
    assert ui["blocks"] == [{"type": "Slot", "card": "trade_approval", "record": record}]


@pytest.mark.asyncio
async def test_a_resolve_card_is_a_settle_slot(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "settle_operation")
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
    record = await resolve_card(db, owner, agent, thread, "watch_changed")
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
        '{"type":"Button","label":"Approve trade"}',
        # Written without diacritics, as the agent writes them.
        '{"type":"Row","children":[{"type":"Button","label":"نفذت"},{"type":"Button","label":"لم تنفذ"}]}',
        '{"type":"Card","title":"طلب موافقة · XAUUSD","children":[{"type":"Text","text":"XAUUSD"}]}',
        '{"type":"Badge","text":"بطاقة ثابتة من Lonora"}',
        '{"type":"Note","text":"This is a fixed card from Lonora."}',
        # A label that becomes a fixed card's word only at a state no option selects.
        '{"type":"Button","label":"{1>2 ? \'Wait\' : \'Approve\'}"}',
        # The frame's own icon.
        '{"type":"Note","text":"راجع الطلب.","icon":"shield"}',
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
    assert imitates_fixed_card("نُفذت") and imitates_fixed_card("نفذت")
    # Invisible format characters and look-alike letters change nothing (zero-width
    # non-joiner, zero-width space, a Cyrillic А, a right-to-left mark).
    assert imitates_fixed_card("موا\u200cفقة") and imitates_fixed_card("رف\u200bض")
    assert imitates_fixed_card("\u0410pprove") and imitates_fixed_card("\u200fرفض")
    assert not imitates_fixed_card("الموافقة على الخطة")
    assert not imitates_fixed_card("Approved plans")
    # A heading is held to the whole words or a separated segment; a control to its start.
    assert imitates_fixed_card("طلب موافقة · XAUUSD") and imitates_fixed_card("XAUUSD | رفض")
    assert not imitates_fixed_card("Approve the plan's timing")
    assert not imitates_fixed_card("موافقة الشريك على الخطة")
    assert imitates_fixed_card("Approve trade", control=True)
    assert imitates_fixed_card("موافقة على الصفقة", control=True)


@pytest.mark.asyncio
async def test_body_text_option_values_and_state_may_use_a_fixed_cards_words(
    task_db: Fixture,
) -> None:
    """Only headings and control labels are held to a fixed card's words: a sentence, a
    stored value or a fallback may use them."""
    db, owner, agent, thread = task_db
    text = card(
        '{"type":"Text","text":"موافقة المالك تأتي من بطاقة الطلب نفسها."}',
        '{"type":"Segmented","bind":"view","label":"العرض","options":[{"value":"approve","label":"الملخّص"},{"value":"reject","label":"التفاصيل"}]}',
    ).replace(
        '{"v":2,"kind":"receipt","title":"ينتظر قرارك","icon":"check"}',
        '{"v":2,"kind":"receipt","title":"ينتظر قرارك","icon":"check"}\n{"state":{"view":"approve"}}',
    )
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics


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


def test_the_refused_words_are_the_clients_own_fixed_card_and_frame_strings() -> None:
    """FIXED_LABELS and FRAME_MARKS copy what the clients draw; a renamed client string
    fails here instead of silently opening the imitation check."""
    from pathlib import Path

    from lonora_agent.genui_compile import FIXED_LABELS, FRAME_MARKS

    root = Path(__file__).parents[1]
    sources = "\n".join(
        (root / path).read_text()
        for path in (
            "apps/web/src/i18n/locales/ar/messages.po",
            "apps/web/src/i18n/locales/en/messages.po",
            "packages/core/src/owner-actions.ts",
            "apps/mobile/lib/i18n.ts",
        )
    )
    for label in FIXED_LABELS:
        assert f'"{label}"' in sources, label
    for mark in FRAME_MARKS:
        assert mark in sources.lower(), mark
