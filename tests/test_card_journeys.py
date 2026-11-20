"""Card journeys (WP-F cards) through the tools and the owner routes.

Expired trade approvals are never executed and «طلب جديد» only asks the agent again; the
owner's «تمديد» moves a watch's expiry later. Runs on the real migrated PostgreSQL schema
with the simulation broker (skipped without ``LONORA_DATABASE_URL``).
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select
from test_proactive_wakes import call, database, retire, simulation


async def raw(fixture: Any, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    response = await fixture.client.request(method, "/api" + path, json=body)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_an_expired_approval_is_never_executed_and_renew_only_asks_again() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow

    fixture = await Fixture().open()
    db = fixture.runtime.db
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Ask me", supervised=True)
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "stop_loss": "95",
            "tolerance": "2",
            "reason": "Fixture entry",
        }
        tool_call = ToolCall(id="buy-" + uuid4().hex, name="trade_execute", arguments=entry)
        registry = load_tools()
        asked = await registry.execute(tool_call, context)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        approval_id = asked["approval_id"]
        async with db.sessions() as session, session.begin():
            row = await session.get(TradeApprovalRow, approval_id, with_for_update=True)
            assert row is not None
            # A new card has no time limit; a card stored before the lifetime was removed
            # keeps its stored expiry, and past it can never be approved.
            assert row.expires_at is None
            row.expires_at = utcnow() - timedelta(seconds=1)
        status, refused = await raw(
            fixture, "POST", f"/trading/approvals/{approval_id}/decision", {"decision": "approve"}
        )
        assert (status, refused["code"]) == (409, "trade_approval_expired"), refused
        status, listed = await raw(fixture, "GET", "/trading/approvals?thread_id=" + thread["id"])
        card = next(item for item in listed if item["id"] == approval_id)
        assert card["status"] == "expired" and card["expires_at"], card
        # The same call, woken again, sends nothing: the card expired unapproved.
        again = await registry.execute(tool_call, context)
        assert again["code"] == "trade_approval_expired" and again["status"] == "expired", again
        async with db.sessions() as session:
            sent = await session.scalar(
                select(func.count())
                .select_from(TradingJournalRow)
                .where(TradingJournalRow.account_id == connection)
            )
            approvals = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.thread_id == thread["id"])
            )
        assert sent == 0
        # «طلب جديد» asks the same agent again in the same conversation; no card is made.
        status, renewed = await raw(fixture, "POST", f"/trading/approvals/{approval_id}/renew")
        assert status == 200, renewed
        assert renewed["agent_id"] == agent["id"] and renewed["thread_id"] == thread["id"]
        status, repeated = await raw(fixture, "POST", f"/trading/approvals/{approval_id}/renew")
        assert status == 200 and repeated["id"] == renewed["id"]
        async with db.sessions() as session:
            run = await session.get(RunRow, renewed["id"])
            assert run is not None and run.trigger == "owner_card"
            assert approval_id in run.prompt and "trade_execute" in run.prompt
            assert run.model_metadata["renews_trade_approval_id"] == approval_id
            after = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.thread_id == thread["id"])
            )
            stored = await session.get(TradeApprovalRow, approval_id)
        assert after == approvals and stored is not None and stored.status == "expired"
        # A card still waiting is answered, not renewed.
        fresh = await call(context, "trade_execute", **{**entry, "volume": "0.2"})
        status, refused = await raw(
            fixture, "POST", f"/trading/approvals/{fresh['approval_id']}/renew"
        )
        assert (status, refused["code"]) == (409, "trade_approval_not_renewable"), refused
        async with db.sessions() as session, session.begin():
            for item in await session.scalars(
                select(RunRow).where(RunRow.id == renewed["id"], RunRow.status == "queued")
            ):
                item.status = "cancelled"
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_agents_watch_update_and_the_owners_extend_move_the_expiry() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MarketWatchRow

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Watcher")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        start = (utcnow() + timedelta(hours=1)).replace(microsecond=0)
        watch = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            kind="price",
            condition="below",
            level="90",
            prompt="Re-check gold below 90",
            expires_at=start.isoformat(),
        )

        async def expiry() -> datetime:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(MarketWatchRow, watch["id"])
                assert row is not None
                return datetime.fromisoformat(str(row.payload["expires_at"]))

        await call(
            context,
            "watch_update",
            watch_id=watch["id"],
            expires_at=(start + timedelta(hours=2)).isoformat(),
        )
        # Moved earlier: the expiry follows.
        await call(
            context,
            "watch_update",
            watch_id=watch["id"],
            expires_at=(start + timedelta(hours=1)).isoformat(),
        )
        assert await expiry() == start + timedelta(hours=1)
        # The owner's «تمديد ساعتين»: two hours later.
        status, extended = await raw(
            fixture, "POST", f"/watches/{watch['id']}/control", {"action": "extend", "hours": 2}
        )
        assert status == 200, extended
        assert await expiry() == start + timedelta(hours=3)
        for body in (
            {"action": "extend"},
            {"action": "extend", "hours": 0},
            {"action": "extend", "hours": 25},
            {"action": "pause", "hours": 2},
        ):
            status, _ = await raw(fixture, "POST", f"/watches/{watch['id']}/control", body)
            assert status == 422, body
        # The owner's own new watch goes through the same watch service.
        status, created = await raw(
            fixture,
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "account_id": connection,
                    "symbol": "XAUUSD",
                    "kind": "price",
                    "condition": "below",
                    "level": "2330",
                    "prompt": "XAUUSD below 2330",
                    "expires_at": (utcnow() + timedelta(hours=4)).isoformat(),
                },
            },
        )
        assert status == 201 and created["agent_id"] == agent["id"], created
        assert created["thread_id"] == thread["id"]
    finally:
        await retire(fixture, connection)
        await fixture.close()
