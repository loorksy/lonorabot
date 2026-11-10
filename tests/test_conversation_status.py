"""The conversation's status surfaces (UI phase 3, WP-F status half).

Pure: the provider failure family (Q22) and the operation words. PostgreSQL
(LONORA_DATABASE_URL, the owner API on the migrated schema): ``run.failed`` carries the
family and the provider's retry hint; ``POST /runs/{id}/retry`` re-runs the same reply once
and never a Run that touched the executor; journal operations carry their conversation
anchor (Q30); the live state names the current work and the pending card.
"""

import os
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from lonora_core.runtime_failure import failure_family, retry_after_seconds
from lonora_db.agent_state import operation_title

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


def test_operation_title_uses_the_reference_order_words():
    assert operation_title({"action": "buy", "volume": "0.1", "symbol": "XAUUSD"}) == (
        "شراء 0.10 XAUUSD"
    )
    assert operation_title({"action": "close_position", "symbol": "EURUSD"}) == "إغلاق EURUSD"


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
                            execution_mode="live",
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
        assert state["current_work"] == {
            "kind": "searching",
            "text": "ابحث عن أخبار الفائدة",
            "until": None,
            "run_id": run_id,
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
        assert state["current_work"]["text"] == "طلب موافقة · بيع 0.20 XAUUSD"
        async with fixture.runtime.db.sessions() as session, session.begin():
            approval = await session.get(TradeApprovalRow, approval_id)
            assert approval is not None
            approval.status = "rejected"
    finally:
        await fixture.close()


def test_anchors_are_written_beside_the_reservation_and_read_by_no_execution_path():
    """Money safety: the anchor is presentation metadata. The live and shadow executors
    write it right after their own reservation; no trading, tool or authority path filters
    or decides on it (only the owner's journal listing does)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("execution.py", "shadow.py"):
        source = (root / "packages/trading/src/lonora_trading" / name).read_text()
        reserved = source.index("await reserve_operation(")
        assert reserved < source.index("await anchor_operation(", reserved), name
    for package in ("trading", "tools", "agent-runtime"):
        for path in (root / "packages" / package / "src").rglob("*.py"):
            text = path.read_text()
            assert "TradingJournalRow.thread_id" not in text, path
            assert "TradingJournalRow.timeline_seq" not in text, path
