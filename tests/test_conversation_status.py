"""The conversation's status surfaces (UI phase 3, WP-F status half).

Pure: the provider failure family (Q22) and the operation words. PostgreSQL
(LONORA_DATABASE_URL, the owner API on the migrated schema): ``run.failed`` carries the
family and the provider's retry hint; ``POST /runs/{id}/retry`` re-runs the same reply once
and never a Run that touched the executor; journal operations carry their conversation
anchor (Q30); the live state names the current work and the pending card.
"""

import json
import os
import re
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from lonora_core.runtime_failure import failure_family, retry_after_seconds
from lonora_db.agent_state import operation_facts

# --- Pure ---------------------------------------------------------------------------


def test_failure_family_follows_the_provider_reason_then_the_code():
    assert failure_family("model_billing_exhausted") == "quota"
    assert failure_family("model_rate_limited") == "rate"
    # A provider timeout shares its code with outages; the classified reason tells.
    assert failure_family("model_provider_unavailable", "timeout") == "timeout"
    assert failure_family("model_provider_unavailable") == "model"
    assert failure_family("model_endpoint_unavailable") == "model"
    assert failure_family("context_limit_exceeded") == "model"
    assert failure_family("tool_read_timeout") == "timeout"
    assert failure_family("runtime_error") == "other"
    assert failure_family(None) == "other"
    assert retry_after_seconds(12.2) == 13
    assert retry_after_seconds(None) is None and retry_after_seconds(0) is None


def test_operation_facts_are_codes_and_numbers_never_server_prose():
    """M8: the operation is data (action code, volume, market); the clients word it."""
    assert operation_facts({"action": "buy", "volume": "0.1", "symbol": "XAUUSD"}) == {
        "action": "buy",
        "volume": "0.10",
        "symbol": "XAUUSD",
    }
    assert operation_facts({"action": "close_position", "symbol": "EURUSD"}) == {
        "action": "close_position",
        "symbol": "EURUSD",
    }


# --- PostgreSQL ------------------------------------------------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The conversation status cases use the real migrated PostgreSQL schema.")


async def conversation_run(fixture: Any, text: str = "حلّل الذهب") -> tuple[dict[str, Any], str]:
    agent = await fixture.agent("Status")
    thread = await fixture.conversation(agent)
    sent = await fixture.request(
        "POST",
        f"/threads/{thread['id']}/messages",
        {"content": text, "client_nonce": "status-" + uuid4().hex},
    )
    return thread, sent["run_ids"][0]


async def failed(
    fixture: Any, run_id: str, code: str, *, reason: str | None = None, retry: float | None = None
) -> None:
    from lonora_db.runs import fail_run

    context = await fixture.lease({"id": run_id, **await fixture.request("GET", f"/runs/{run_id}")})
    async with fixture.runtime.db.sessions() as session, session.begin():
        await fail_run(session, context.lease, code, reason=reason, retry_after=retry)


async def post(fixture: Any, path: str) -> Any:
    return await fixture.client.request("POST", "/api" + path)


async def age(fixture: Any, run_id: str, seconds: int) -> None:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id)
        assert row is not None
        row.updated_at = utcnow() - timedelta(seconds=seconds)


@pytest.mark.asyncio
async def test_failed_run_reports_its_family_and_retries_once_after_the_wait():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture)
        original = await fixture.request("GET", f"/runs/{run_id}")
        assert original["failure"] is None
        await failed(fixture, run_id, "model_rate_limited", reason="rate_limit", retry=29.5)
        run = await fixture.request("GET", f"/runs/{run_id}")
        assert run["failure"] == {"family": "rate", "retry_after_seconds": 30}
        async with fixture.runtime.db.sessions() as session:
            event = await session.scalar(
                select(EventRow).where(EventRow.run_id == run_id, EventRow.kind == "run.failed")
            )
        assert event is not None
        assert event.payload["failure"] == {"family": "rate", "retry_after_seconds": 30}
        # During the provider's wait the retry says how long is left; nothing is created.
        early = await post(fixture, f"/runs/{run_id}/retry")
        assert early.status_code == 409 and early.json()["code"] == "run_retry_too_early"
        assert 0 < early.json()["retry_after_seconds"] <= 30
        await age(fixture, run_id, 31)
        response = await post(fixture, f"/runs/{run_id}/retry")
        assert response.status_code == 202
        retry = response.json()
        assert retry["id"] != run_id and retry["status"] == "queued"
        assert (retry["thread_id"], retry["agent_id"], retry["trigger"], retry["input_seq"]) == (
            thread["id"],
            original["agent_id"],
            original["trigger"],
            original["input_seq"],
        )
        assert retry["model_metadata"]["retry_of"] == run_id
        # Idempotent per failed Run: the same new Run, not a second one.
        again = await post(fixture, f"/runs/{run_id}/retry")
        assert again.status_code == 202 and again.json()["id"] == retry["id"]
        # A Run that did not fail is not retryable.
        refused = await post(fixture, f"/runs/{retry['id']}/retry")
        assert refused.status_code == 409 and refused.json()["code"] == "run_not_retryable"
        missing = await post(fixture, f"/runs/{uuid4()}/retry")
        assert missing.status_code == 404
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_run_that_touched_the_executor_is_never_retried():
    """Money safety: any journal operation or trade approval of the Run blocks the retry,
    whatever its outcome, so a retry can never repeat a trade."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow

    fixture = await Fixture().open()
    try:
        for touch in ("journal", "approval"):
            thread, run_id = await conversation_run(fixture)
            await failed(fixture, run_id, "model_provider_unavailable")
            async with fixture.runtime.db.sessions() as session, session.begin():
                run = await session.get(RunRow, run_id)
                assert run is not None
                if touch == "journal":
                    session.add(
                        TradingJournalRow(
                            operation_id="op-retry-" + uuid4().hex,
                            owner_id=fixture.owner,
                            account_id="acct",
                            request_hash="hash",
                            request={"action": "buy", "symbol": "XAUUSD", "volume": "0.1"},
                            status="failed",
                            result={"details": {"execution": {"run_id": run_id}}},
                        )
                    )
                else:
                    session.add(
                        TradeApprovalRow(
                            id=str(uuid4()),
                            owner_id=fixture.owner,
                            run_id=run_id,
                            thread_id=thread["id"],
                            agent_id=run.agent_id,
                            call_id="call",
                            requests=[{"action": "buy", "symbol": "XAUUSD"}],
                            status="rejected",
                            results=[],
                        )
                    )
            response = await post(fixture, f"/runs/{run_id}/retry")
            assert response.status_code == 409, touch
            assert response.json()["code"] == "run_not_retryable", touch
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_retry_of_a_spoken_request_stays_provisional_and_is_withdrawn_by_corrections():
    """M2(a): the retry carries the voice provenance, so it cannot spend the standing grant
    without its own approval card, and the correction path selects it."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow
    from lonora_db.voice_provenance import delegation_runs
    from lonora_trading.account_authority import provisional_voice

    fixture = await Fixture().open()
    try:
        _, run_id = await conversation_run(fixture, "اشترِ الذهب")
        handoff = {
            "session_id": "voice-1",
            "delegation_id": "d-1",
            "revision": 1,
            "finalized": False,
        }
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id)
            assert run is not None
            run.model_metadata = {**run.model_metadata, "voice_handoff": handoff}
        await failed(fixture, run_id, "model_provider_unavailable")
        response = await post(fixture, f"/runs/{run_id}/retry")
        assert response.status_code == 202
        retry_id = response.json()["id"]
        async with fixture.runtime.db.sessions() as session:
            retry = await session.get(RunRow, retry_id)
            assert retry is not None
            assert retry.model_metadata["voice_handoff"] == handoff
            assert await provisional_voice(session, retry) is True
            assert set(await session.scalars(delegation_runs("d-1"))) == {run_id, retry_id}
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reply_that_started_other_work_is_never_retried():
    """M2(b): a peer, collaboration, subagent or Task started by the failed reply may hold
    money of its own; the retry is refused whatever that work did."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        for link in ("parent_run_id", "started_by_run_id"):
            thread, run_id = await conversation_run(fixture)
            await failed(fixture, run_id, "model_provider_unavailable")
            async with fixture.runtime.db.sessions() as session, session.begin():
                parent = await session.get(RunRow, run_id)
                assert parent is not None
                child = RunRow(
                    id=str(uuid4()),
                    thread_id=thread["id"],
                    agent_id=parent.agent_id,
                    trigger="tickets",
                    prompt="",
                    input_seq=parent.input_seq,
                    parent_run_id=run_id if link == "parent_run_id" else None,
                    model_metadata={"started_by_run_id": run_id}
                    if link == "started_by_run_id"
                    else {},
                )
                session.add(child)
                # A grandchild two levels down is found too.
                session.add(
                    RunRow(
                        id=str(uuid4()),
                        thread_id=thread["id"],
                        agent_id=parent.agent_id,
                        trigger="tickets",
                        prompt="",
                        input_seq=parent.input_seq,
                        parent_run_id=child.id,
                    )
                )
            response = await post(fixture, f"/runs/{run_id}/retry")
            assert response.status_code == 409, link
            assert response.json()["code"] == "run_not_retryable", link
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reply_that_started_a_real_ticket_or_task_is_never_retried():
    """R4: the real start paths link their work to the starting run (started_by_run_id), so
    POST /runs/{id}/retry refuses the reply that started a ticket or a Task."""
    database()
    from check_streaming import Fixture
    from lonora_agent.automation.background import start_ticket
    from lonora_contracts.tasks import TaskCreate
    from lonora_db.boards import BoardRepository
    from lonora_db.runs import fail_run
    from lonora_db.schema import RunRow
    from lonora_db.tasks import create_task
    from lonora_db.tickets import TicketRepository

    fixture = await Fixture().open()
    try:
        for work in ("ticket", "task"):
            thread, run_id = await conversation_run(fixture)
            run = await fixture.request("GET", f"/runs/{run_id}")
            context = await fixture.lease({"id": run_id, **run})
            db = fixture.runtime.db
            if work == "ticket":
                async with db.sessions() as session, session.begin():
                    board = await BoardRepository().create(
                        session, fixture.owner, {"title": "Work"}, agent_id=run["agent_id"]
                    )
                    ticket = await TicketRepository().create(
                        session,
                        fixture.owner,
                        {"board_id": board.id, "title": "Reconcile", "description": ""},
                        agent_id=run["agent_id"],
                    )
                started = await start_ticket(db, fixture.owner, ticket.id, lease=context.lease)
            else:
                async with db.sessions() as session, session.begin():
                    starter = await session.get(RunRow, run_id)
                    task = await create_task(
                        session,
                        fixture.owner,
                        run["agent_id"],
                        thread["id"],
                        TaskCreate(title="Reconcile", description=""),
                        starter=starter,
                    )
                    started = {"id": task.payload["run_id"]}
            async with db.sessions() as session, session.begin():
                child = await session.get(RunRow, started["id"])
                assert child is not None, work
                assert child.model_metadata["started_by_run_id"] == run_id, work
                await fail_run(session, context.lease, "model_provider_unavailable")
            response = await post(fixture, f"/runs/{run_id}/retry")
            assert response.status_code == 409, work
            assert response.json()["code"] == "run_not_retryable", work
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reply_to_an_edited_message_is_never_retried():
    """M2(c): edit-and-resend replaced the owner's message; its old request never runs again."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture, "اشترِ 0.1 ذهب")
        listed = await fixture.request("GET", f"/threads/{thread['id']}/messages")
        original = next(
            row for row in cast("list[dict[str, Any]]", listed) if row["role"] == "user"
        )
        await failed(fixture, run_id, "model_provider_unavailable")
        await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "حلّل الذهب فقط",
                "client_nonce": "edit-" + uuid4().hex,
                "edited_from": original["id"],
            },
        )
        response = await post(fixture, f"/runs/{run_id}/retry")
        assert response.status_code == 409
        assert response.json()["code"] == "run_not_retryable"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_renewed_approval_keeps_the_spoken_requests_provenance():
    """M2(a): «طلب جديد» on an expired approval of a spoken request starts a provisional
    run whose approvals a later correction withdraws."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow
    from lonora_db.trade_approvals import renew_approval
    from lonora_trading.account_authority import provisional_voice

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture, "اشترِ الذهب")
        handoff = {"session_id": "voice-2", "delegation_id": "d-2", "finalized": False}
        approval_id = str(uuid4())
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id)
            assert run is not None
            run.model_metadata = {**run.model_metadata, "voice_handoff": handoff}
            session.add(
                TradeApprovalRow(
                    id=approval_id,
                    owner_id=fixture.owner,
                    run_id=run_id,
                    thread_id=thread["id"],
                    agent_id=run.agent_id,
                    call_id="call",
                    requests=[{"action": "buy", "symbol": "XAUUSD"}],
                    status="expired",
                    results=[],
                )
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            renewed = await renew_approval(session, fixture.owner, approval_id)
            renewed_id = renewed.id
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, renewed_id)
            assert row is not None
            assert row.model_metadata["voice_handoff"] == handoff
            assert await provisional_voice(session, row) is True
            # The model text of the renewal is English only.
            assert all(ord(ch) < 0x0600 or ord(ch) > 0x06FF for ch in row.prompt)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_journal_operations_carry_their_conversation_anchor():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import EventRow, RunRow, ThreadRow, TradingJournalRow
    from lonora_db.trading_journal import anchor_operation, reserve_operation
    from lonora_trading.operation_events import operation_event
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture, "اشترِ الذهب")
        other, _ = await conversation_run(fixture, "سؤال آخر")
        operation = "op-anchor-" + uuid4().hex
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id)
            conversation = await session.get(ThreadRow, thread["id"])
            assert run is not None and conversation is not None
            row, created = await reserve_operation(
                session,
                fixture.owner,
                operation,
                "acct",
                "hash",
                {"action": "buy", "symbol": "XAUUSD", "volume": "0.1"},
            )
            assert created
            row.status = "reserved"
            row.result = {"details": {"execution": {"run_id": run_id, "agent_id": run.agent_id}}}
            await anchor_operation(session, row, run)
            assert (row.thread_id, row.timeline_seq) == (thread["id"], conversation.next_seq)
            await operation_event(session, row)
        path = f"/trading/journal?thread_id={thread['id']}"
        listed = cast(list[dict[str, Any]], await fixture.request("GET", path))
        assert [item["operation_id"] for item in listed] == [operation]
        assert listed[0]["thread_id"] == thread["id"]
        assert listed[0]["timeline_seq"] == conversation.next_seq
        assert await fixture.request("GET", f"/trading/journal?thread_id={other['id']}") == []
        async with fixture.runtime.db.sessions() as session:
            event = await session.scalar(
                select(EventRow).where(
                    EventRow.kind == "trading.operation_updated",
                    EventRow.payload["operation_id"].as_string() == operation,
                )
            )
        assert event is not None
        assert event.payload["thread_id"] == thread["id"]
        assert event.payload["timeline_seq"] == conversation.next_seq
        async with fixture.runtime.db.sessions() as session, session.begin():
            # Settle the probe so the fixture's agents can be cleaned up.
            settled = await session.get(TradingJournalRow, operation)
            assert settled is not None
            settled.status = "failed"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_live_state_names_the_current_work_and_the_pending_card():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture, "ابحث عن أخبار الفائدة")
        run = await fixture.request("GET", f"/runs/{run_id}")
        agent_id = run["agent_id"]
        await fixture.lease(run)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, run_id)
            assert row is not None
            row.model_metadata = {
                **row.model_metadata,
                "activity": {"kind": "tool.started", "name": "web_search", "toolset": "research"},
            }
        state = await fixture.request("GET", f"/agents/{agent_id}/state")
        # The owner's own words are owner content and stay as data.
        assert state["current_work"] == {
            "kind": "searching",
            "text": "ابحث عن أخبار الفائدة",
            "until": None,
            "run_id": run_id,
            "operation": None,
            "card": None,
        }
        assert state["pending_card_id"] is None
        approval_id = str(uuid4())
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                TradeApprovalRow(
                    id=approval_id,
                    owner_id=fixture.owner,
                    run_id=run_id,
                    thread_id=thread["id"],
                    agent_id=agent_id,
                    call_id="call",
                    requests=[{"action": "sell", "symbol": "XAUUSD", "volume": "0.2"}],
                    status="pending",
                    results=[],
                )
            )
        state = await fixture.request("GET", f"/agents/{agent_id}/state")
        assert state["pending_card_id"] == approval_id
        assert state["current_work"]["kind"] == "waiting_owner"
        # M8: no server-written prose (in any language): codes and the operation's facts.
        assert state["current_work"]["text"] == ""
        assert state["current_work"]["card"] == "trade_approval"
        assert state["current_work"]["operation"] == {
            "action": "sell",
            "volume": "0.20",
            "symbol": "XAUUSD",
        }
        arabic = re.compile("[\u0600-\u06ff]")
        async with fixture.runtime.db.sessions() as session:
            from lonora_db.agent_state import agent_live_state

            live = await agent_live_state(session, fixture.owner, agent_id)
            frame = live.model_dump(mode="json", include={"current_work", "pending_card_id"})
            assert not arabic.search(json.dumps(frame, ensure_ascii=False)), frame
        async with fixture.runtime.db.sessions() as session, session.begin():
            approval = await session.get(TradeApprovalRow, approval_id)
            assert approval is not None
            approval.status = "rejected"
    finally:
        await fixture.close()


def test_anchors_are_written_beside_the_reservation_and_read_by_no_execution_path():
    """Money safety: the anchor is presentation metadata. The executor writes it right
    after its own reservation; no trading, tool or authority path filters
    or decides on it (only the owner's journal listing does)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("execution.py",):
        source = (root / "packages/trading/src/lonora_trading" / name).read_text()
        reserved = source.index("await reserve_operation(")
        assert reserved < source.index("await anchor_operation(", reserved), name
    for package in ("trading", "tools", "agent-runtime"):
        for path in (root / "packages" / package / "src").rglob("*.py"):
            text = path.read_text()
            assert "TradingJournalRow.thread_id" not in text, path
            assert "TradingJournalRow.timeline_seq" not in text, path


@pytest.mark.asyncio
async def test_the_routing_frame_never_carries_the_owners_status_line():
    """M8: current_work and its card pointer are the owner's (Arabic) status line; model text
    is English only, so the routing frame leaves them out."""
    database()
    from check_streaming import Fixture
    from lonora_agent.context.team import routing_frame
    from lonora_db.agent_state import agent_live_state
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        thread, run_id = await conversation_run(fixture, "اشترِ الذهب")
        # Running: the owner's line then names the message it answers.
        await fixture.lease({"id": run_id, **await fixture.request("GET", f"/runs/{run_id}")})
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, run_id)
            assert run is not None
            live = await agent_live_state(session, fixture.owner, run.agent_id)
            frame = await routing_frame(session, fixture.owner, run.agent_id, thread["id"])
        assert live.current_work is not None  # the owner's line exists ...
        assert '"current_work"' not in frame and '"pending_card_id"' not in frame  # ... not here
        assert "اشترِ الذهب" not in frame
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_limit_validation_codes_reach_the_client():
    """M11: an owner-actionable limit error keeps its own code (the client says what to fix),
    never the generic invalid_request."""
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        path = f"/api/trading/accounts/{uuid4()}/execution-policy"
        missing = await fixture.client.request(
            "PUT", path, json={"risk": {"max_daily_loss": "100"}}
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "risk_currency_required"
        zone = await fixture.client.request(
            "PUT",
            path,
            json={"risk": {"currency": "USD", "trading_day_timezone": "Mars/Olympus"}},
        )
        assert zone.status_code == 422
        assert zone.json()["code"] == "trading_day_timezone_invalid"
    finally:
        await fixture.close()
