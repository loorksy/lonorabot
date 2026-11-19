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
from lonora_agent.genui_compile import SLOT_HEIGHTS, imitates_fixed_card, shows_frame_mark
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
HEAD = '{"v":2,"kind":"summary","title":"ينتظر قرارك","icon":"check"}'
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
        mandate = kind == "trading_mode"
        secret = kind == "secret"
        made = await create_card(
            session,
            owner,
            card_id=f"{kind}-card",
            agent_id=agent,
            thread=row,
            run_id=None,
            source="agent" if mandate or secret else "system",
            kind=kind,
            subject=(
                "trading_mode:" + agent
                if mandate
                else "secret:exchange"
                if secret
                else "operation:op-1"
            ),
            payload=(
                {"agent_id": agent}
                if mandate
                else SECRET_CARD
                if secret
                else {"operation_id": "op-1"}
            ),
        )
        return made.id


# A Secret card as W-ENV's card stores it: the agent's label and fields, the server's
# destination (7.2.3).
SECRET_CARD = {
    "label": "Exchange",
    "connect": None,
    "fields": [{"key": "EXCHANGE_KEY", "label": "Key", "secret": True}],
    "destination": "workspace",
}


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
async def test_a_mandate_card_is_a_mandate_slot_and_no_other(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "trading_mode")
    ui, projector = await project(db, owner, agent, thread, card(slot(record, "mandate")))
    assert ui is not None, projector.diagnostics
    assert ui["blocks"] == [{"type": "Slot", "card": "mandate", "record": record}]
    for kind in ("settle", "trade_approval", "secret"):
        ui, projector = await project(db, owner, agent, thread, card(slot(record, kind)))
        assert ui is None and "card_fallback_slot" in codes(projector), kind
    settle = await resolve_card(db, owner, agent, thread, "settle_operation")
    ui, projector = await project(db, owner, agent, thread, card(slot(settle, "mandate")))
    assert ui is None and "card_fallback_slot" in codes(projector)


@pytest.mark.asyncio
async def test_a_secret_card_is_a_secret_slot_and_no_other(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "secret")
    ui, projector = await project(db, owner, agent, thread, card(slot(record, "secret")))
    assert ui is not None, projector.diagnostics
    assert ui["blocks"] == [{"type": "Slot", "card": "secret", "record": record}]
    for kind in ("settle", "trade_approval"):
        ui, projector = await project(db, owner, agent, thread, card(slot(record, kind)))
        assert ui is None and "card_fallback_slot" in codes(projector), kind
    settle = await resolve_card(db, owner, agent, thread, "settle_operation")
    ui, projector = await project(db, owner, agent, thread, card(slot(settle, "secret")))
    assert ui is None and "card_fallback_slot" in codes(projector)


async def secret_with_fields(db: Database, owner: str, agent: str, thread: str, count: int):
    async with db.sessions() as session, session.begin():
        row = await session.get(ThreadRow, thread)
        assert row is not None
        made = await create_card(
            session,
            owner,
            card_id=f"secret-{count}-fields",
            agent_id=agent,
            thread=row,
            run_id=None,
            source="agent",
            kind="secret",
            subject=f"secret:fields:{count}",
            payload={
                **SECRET_CARD,
                "fields": [
                    {"key": f"KEY_{index}", "label": f"Key {index}", "secret": True}
                    for index in range(count)
                ],
            },
        )
        return made.id


@pytest.mark.asyncio
async def test_a_secret_slot_counts_its_fields_and_too_many_fall_back(task_db: Fixture) -> None:
    """A Secret card grows 95 px a field (10.1.4): its slot counts what the owner will see,
    the agent's other blocks fold first, and a card the slot alone pushes past 720 px falls
    back, which brings the card's own row back."""
    db, owner, agent, thread = task_db
    note = '{"type":"Note","text":"أحتاج المفاتيح لأقرأ حسابك في المنصة."}'
    one = await secret_with_fields(db, owner, agent, thread, 1)
    ui, projector = await project(db, owner, agent, thread, card(note, slot(one, "secret")))
    assert ui is not None and "budget_folded" not in codes(projector), projector.diagnostics
    two = await secret_with_fields(db, owner, agent, thread, 2)
    ui, projector = await project(db, owner, agent, thread, card(note, slot(two, "secret")))
    # 305 + 2 × 95 = 495 px with the head is over 560 at rest: the note folds, never the
    # slot, and the card (649 px) stays under 720.
    assert ui is not None, projector.diagnostics
    assert "budget_folded" in codes(projector)
    assert {block["type"] for block in ui["blocks"]} == {"More", "Slot"}
    three = await secret_with_fields(db, owner, agent, thread, 3)
    ui, projector = await project(db, owner, agent, thread, card(slot(three, "secret")))
    assert ui is not None, projector.diagnostics  # 690 px, alone
    ui, projector = await project(db, owner, agent, thread, card(note, slot(three, "secret")))
    assert ui is None and "card_fallback_budget" in codes(projector)  # 744 px with its fold
    eight = await secret_with_fields(db, owner, agent, thread, 8)
    ui, projector = await project(db, owner, agent, thread, card(slot(eight, "secret")))
    assert ui is None and "card_fallback_budget" in codes(projector)


@pytest.mark.asyncio
async def test_an_owner_action_of_another_kind_is_not_a_settle_slot(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    record = await resolve_card(db, owner, agent, thread, "trading_mode")
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
        '{"type":"Button","label":"وكّله"}',
        '{"type":"Card","title":"التفويض","children":[{"type":"Badge","text":"يستأذن"}]}',
        '{"type":"Button","label":"Full"}',
        # The Mandate card's state line, in a sentence's place.
        '{"type":"Text","text":"الذهب · الآن: وكّله"}',
        '{"type":"Card","title":"بيانات سرّية","children":[{"type":"Text","text":"المفتاح"}]}',
        '{"type":"Card","title":"Secret · Binance","children":[{"type":"Text","text":"Key"}]}',
        '{"type":"Badge","text":"ربط حساب التداول"}',
        '{"type":"Title","text":"New MetaApi API token"}',
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
    # The Secret card's titles, both languages, the broker ones included.
    assert imitates_fixed_card("Secret") and imitates_fixed_card("Secret · Binance")
    assert imitates_fixed_card("كلمة مرور تداول جديدة")
    assert not imitates_fixed_card("Secret of a good entry")
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
    # The Settle card's Unknown button is a control's word only: a heading or a badge that
    # says a value is unknown is an ordinary label, a button that says it is refused.
    assert not imitates_fixed_card("غير معروفة") and not imitates_fixed_card("Unknown")
    assert imitates_fixed_card("غير معروفة", control=True)
    assert imitates_fixed_card("Unknown outcome", control=True)
    # Everyday words a fixed card also says («Full», «Ask») are refused only as a whole
    # Button label: a Bid/Ask quote or a «Full» close size is an ordinary card.
    assert imitates_fixed_card("Full", control=True) and imitates_fixed_card("ask", control=True)
    assert not imitates_fixed_card("Full report", control=True)
    assert not imitates_fixed_card("Ask") and not imitates_fixed_card("Full")
    # The Mandate card's state line, wherever it is shown.
    assert shows_frame_mark("الذهب · الآن: وكّله") and shows_frame_mark("Now: Full")
    assert shows_frame_mark("Gold · Now: Ask") and shows_frame_mark("**Now:** Full")
    assert shows_frame_mark("وكيل الذهب\nالآن : يستأذن")
    # After the name and any punctuation, not only the card's own separators.
    assert shows_frame_mark("الذهب، الآن: وكّله") and shows_frame_mark("الذهب: الآن: يستأذن")
    assert shows_frame_mark("Gold: Now: Full") and shows_frame_mark("Gold, Now: Ask")
    for dot in "\u2219\u22c5\u30fb":
        assert shows_frame_mark(f"Gold {dot} Now: Full"), dot
    assert shows_frame_mark("الذهب، الآن: وكّله · منذ اليوم")
    assert not shows_frame_mark("Full now") and not shows_frame_mark("الآن السعر 2400")
    # Only in that form: a sentence with the same words says nothing about a mode.
    assert not shows_frame_mark("You can now ask me for the weekly report.")
    assert not shows_frame_mark("The book is now full.")
    assert not shows_frame_mark("السوق هادئ الآن وكله ترقب")
    assert not shows_frame_mark("What to do now: ask your broker for the fill.")
    assert not shows_frame_mark("Next step, now: ask your broker for the fill.")
    assert not shows_frame_mark("قرّرت الآن: يستأذن قبل كل صفقة")
    assert not shows_frame_mark("الخطة: الآن نراقب، ثم يستأذن")


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
        '{"v":2,"kind":"summary","title":"ينتظر قرارك","icon":"check"}',
        '{"v":2,"kind":"summary","title":"ينتظر قرارك","icon":"check"}\n{"state":{"view":"approve"}}',
    )
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics


@pytest.mark.asyncio
async def test_a_sentence_may_say_now_ask_or_now_full(task_db: Fixture) -> None:
    """Only the Mandate card's state line («الآن: وكّله») is its words; a sentence that uses
    them is the agent's own."""
    db, owner, agent, thread = task_db
    text = card(
        '{"type":"Text","text":"You can now ask me for the weekly report."}',
        '{"type":"Note","text":"السوق هادئ الآن وكله ترقب."}',
    )
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics


@pytest.mark.asyncio
async def test_a_badge_may_say_a_value_is_unknown(task_db: Fixture) -> None:
    """«غير معروفة» is the Settle card's button word, refused only as a control's label."""
    db, owner, agent, thread = task_db
    text = card('{"type":"Badge","text":"غير معروفة","tone":"warn"}')
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics
    refused = card('{"type":"Button","label":"غير معروفة"}')
    ui, projector = await project(db, owner, agent, thread, refused)
    assert ui is None


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
    """FIXED_LABELS, FIXED_CONTROL_LABELS, FIXED_WHOLE, the state line's words and FRAME_MARKS
    copy what the clients draw; a renamed client string fails here instead of silently opening
    the imitation check."""
    from pathlib import Path

    from lonora_agent.genui_compile import (
        FIXED_CONTROL_LABELS,
        FIXED_LABELS,
        FIXED_WHOLE,
        FRAME_MARKS,
        MODE_NOW,
        MODE_WORDS,
    )

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
    for label in FIXED_LABELS + FIXED_CONTROL_LABELS + FIXED_WHOLE + MODE_NOW + MODE_WORDS:
        assert f'"{label}"' in sources, label
    for mark in FRAME_MARKS:
        assert mark in sources.lower(), mark


@pytest.mark.asyncio
async def test_a_bid_ask_quote_and_a_full_close_size_are_ordinary_cards(task_db: Fixture) -> None:
    """«Full» and «Ask» are the Mandate card's words only as a whole Button label."""
    db, owner, agent, thread = task_db
    text = card(
        '{"type":"Grid","cols":2,"children":[{"type":"Stat","label":"Bid","value":"—"},{"type":"Stat","label":"Ask","value":"—"}]}',
        '{"type":"Segmented","bind":"size","label":"Close","options":[{"value":"full","label":"Full"},{"value":"half","label":"Half"}]}',
    ).replace(HEAD, HEAD + '\n{"state":{"size":"full"}}')
    ui, projector = await project(db, owner, agent, thread, text)
    assert ui is not None, projector.diagnostics
