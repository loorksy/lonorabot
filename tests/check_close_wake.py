"""A closed trade wakes its owner, which writes a short self-review (mandate 5.5.2).

Done when a stop-loss hit and the agent's own close both end with a new memory
revision. A stop-loss hit (no Run of the agent closed it) starts a broker_event Run;
the agent's own close, while its closing Run still executes, reaches that Run as a
notice, never a second Run. A paused agent is woken for its own trade; the owner's
own trade wakes nobody; a notice its Run never read becomes a Run; each trade wakes once.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.memory import read_memory
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import claim_next
from lonora_db.schema import (
    AgentRow,
    ClosedTradeRow,
    EffectReceiptRow,
    MemoryRevisionRow,
    MessageRow,
    RunRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from lonora_trading.close_wake import MAXIMUM_PER_PASS, wake_for_closes
from sqlalchemy import func, select

SELECTION = ModelSelection(provider="openai", model="scripted-close")
CLOSED = "A trade you owned has closed at the broker"


async def closed(
    f: Fixture,
    account: str,
    agent_id: str | None,
    closing_order: str,
    pnl: str | None,
    *,
    operation_id: str | None = None,
    closed_ago: timedelta = timedelta(0),
) -> str:
    """A ledger row as W-LEDGER writes it: the trade's broker deals, its P&L and owner.
    ``operation_id`` is what the simulation broker's history names on the exit deal."""
    trade = new_id()
    now = utcnow() - closed_ago
    async with f.runtime.db.sessions() as session, session.begin():
        session.add(
            ClosedTradeRow(
                id=trade,
                owner_id=f.owner,
                account_id=account,
                position_id="pos-" + trade[:8],
                closing_deal_id="deal-out-" + trade[:8],
                symbol="XAUUSD",
                side="buy",
                volume=Decimal("0.5"),
                agent_id=agent_id,
                label="secure_then_add",
                currency="USD",
                realized_pnl=Decimal(pnl) if pnl else None,
                opened_at=now - timedelta(hours=3),
                closed_at=now,
                deals=[
                    {"id": "deal-in-" + trade[:8], "orderId": "pos-" + trade[:8]},
                    {
                        "id": "deal-out-" + trade[:8],
                        "orderId": closing_order,
                        **({"operation_id": operation_id} if operation_id else {}),
                    },
                ],
            )
        )
    return trade


async def revisions(f: Fixture, agent_id: str) -> int:
    async with f.runtime.db.sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MemoryRevisionRow)
                .where(MemoryRevisionRow.agent_id == agent_id)
            )
            or 0
        )


async def runs_of(f: Fixture, agent_id: str, trigger: str) -> list[RunRow]:
    async with f.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow).where(RunRow.agent_id == agent_id, RunRow.trigger == trigger)
            )
        )


def reviewer(
    version: int,
    seen: list[list[ModelMessage]],
    *,
    read_first: bool = False,
    final: str = "Reviewed.",
) -> Any:
    """A model that answers the close text with a self-review in its memory; with
    ``read_first`` its first turn is a tool call, so the text arrives after a tool block."""

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
        if read_first and len(seen) == 1:
            return ModelReply(
                tool_calls=[ToolCall(id="read-first", name="memory_read", arguments={})]
            ), SELECTION
        text = "\n".join(message.content for message in messages)
        reviewed = any(
            call.name == "memory_write" for message in messages for call in message.tool_calls
        )
        if CLOSED in text and not reviewed:
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="review-" + new_id()[:8],
                        name="memory_write",
                        arguments={
                            "version": version,
                            "operations": [
                                {
                                    "action": "add",
                                    "section": "MEMORY.md",
                                    "content": "Review XAUUSD: secured then added; stop held "
                                    "the gain. Keep the break-even step before adding.",
                                }
                            ],
                        },
                    )
                ]
            ), SELECTION
        return ModelReply(text=final), SELECTION

    return complete


async def memory_version(f: Fixture, agent_id: str) -> int:
    async with f.runtime.db.sessions() as session:
        return (await read_memory(session, f.owner, agent_id)).version


async def stop_loss_hit(f: Fixture, account: str) -> None:
    agent = await f.agent("Gold stop")
    before = await revisions(f, agent["id"])
    trade = await closed(f, account, agent["id"], "sl-order", "-12.5")
    # A first read of a connection backfills old trades: they are not news.
    await closed(f, account, agent["id"], "sl-old", "7", closed_ago=timedelta(days=30))
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # once per trade
    (run,) = await runs_of(f, agent["id"], "broker_event")
    assert CLOSED in run.prompt and '"realized_pnl": "-12.5"' in run.prompt
    assert '"label": "secure_then_add"' in run.prompt and trade[:8] in run.prompt
    assert run.model_metadata["closed_trade_id"] == trade
    seen: list[list[ModelMessage]] = []
    data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    ctx = await f.lease(data)
    posted = await messages_in(f, run.model_metadata["origin_thread_id"])
    # The review needs nothing from the owner: the Run ends without a reply.
    version = await memory_version(f, agent["id"])
    with patch.object(ctx.router, "complete", reviewer(version, seen, final="")):
        await execute_run(ctx, load_tools(), 120, 8)
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    async with f.runtime.db.sessions() as session:
        done = await session.get(RunRow, run.id)
        assert done and done.status == "completed", done and (done.status, done.error_code)
    assert await messages_in(f, run.model_metadata["origin_thread_id"]) == posted
    assert len(seen) == 2, "the empty reply was nudged into a chat message"
    print("PASS a stop-loss hit wakes the position's owner, which writes a self-review")
    print("PASS a review that needs nothing from the owner posts nothing in the chat")


async def messages_in(f: Fixture, thread_id: str) -> int:
    async with f.runtime.db.sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.thread_id == thread_id)
            )
            or 0
        )


async def many_woken(f: Fixture, account: str) -> None:
    """Trades already woken never crowd out a new close (more than a pass's limit)."""
    agent = await f.agent("Gold busy")
    async with f.runtime.db.sessions() as session, session.begin():
        for _ in range(MAXIMUM_PER_PASS + 10):
            trade = new_id()
            session.add(
                ClosedTradeRow(
                    id=trade,
                    owner_id=f.owner,
                    account_id=account,
                    position_id="old-" + trade[:8],
                    closing_deal_id="old-out-" + trade[:8],
                    symbol="XAUUSD",
                    side="buy",
                    volume=Decimal("0.1"),
                    agent_id=agent["id"],
                    currency="USD",
                    realized_pnl=Decimal(1),
                    closed_at=utcnow(),
                    deals=[],
                )
            )
            session.add(EffectReceiptRow(key="close-wake:" + trade, result={"run_id": None}))
    fresh = await closed(f, account, agent["id"], "sl-busy", "2")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (run,) = await runs_of(f, agent["id"], "broker_event")
    assert run.model_metadata["closed_trade_id"] == fresh
    print("PASS woken trades never crowd out a new close")


async def busy_notices(f: Fixture, account: str) -> None:
    """Unread notices of a still-executing Run never crowd out one whose Run ended."""
    agent = await f.agent("Gold notices")
    thread = await f.conversation(agent)
    busy = await f.run(agent, thread)
    await f.lease(busy)  # executing
    ended = await f.run(agent, thread)
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, ended["id"])
        assert row
        row.status = "completed"
    trades: list[str] = []
    # More than the 200 candidates an unfiltered scan used to read.
    for _ in range(4 * MAXIMUM_PER_PASS + 10):
        trades.append(await closed(f, account, agent["id"], "n-" + new_id()[:8], "1"))
    last = await closed(f, account, agent["id"], "n-last", "1")
    async with f.runtime.db.sessions() as session, session.begin():
        for trade, run in [*((t, busy["id"]) for t in trades), (last, ended["id"])]:
            session.add(EffectReceiptRow(key="close-wake:" + trade, result={"notice_run_id": run}))
            session.add(
                EffectReceiptRow(
                    key="run-notice:" + run + ":" + trade,
                    result={"run_id": run, "trade_id": trade, "text": "t", "consumed": False},
                )
            )
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (woken,) = await runs_of(f, agent["id"], "broker_event")
    assert woken.model_metadata["closed_trade_id"] == last
    print("PASS notices of an executing Run never crowd out one whose Run ended")


async def deleted_owner(f: Fixture, account: str) -> None:
    """A trade of an agent that no longer exists wakes Lonora, which answers for it."""
    trade = await closed(f, account, new_id(), "sl-gone", "-3")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    async with f.runtime.db.sessions() as session:
        lonora = await ensure_personal_agent(session, f.owner)
    woken = [
        run
        for run in await runs_of(f, lonora.id, "broker_event")
        if run.model_metadata.get("closed_trade_id") == trade
    ]
    assert len(woken) == 1 and "no longer exists" in woken[0].prompt, woken
    print("PASS a deleted agent's closed trade wakes Lonora")


async def own_close(f: Fixture, account: str, *, read_first: bool) -> None:
    agent = await f.agent("Gold manager")
    operation = new_id()
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    ctx = await f.lease(run)  # the closing Run is executing
    async with f.runtime.db.sessions() as session, session.begin():
        session.add(
            # As the simulation broker journals a close: no broker order id in its
            # details; its history names the operation on the exit deal.
            TradingJournalRow(
                operation_id=operation,
                owner_id=f.owner,
                account_id=account,
                request_hash="h",
                request={"account_id": account, "symbol": "XAUUSD", "action": "close_position"},
                status="confirmed",
                result={
                    "status": "confirmed",
                    "broker_id": "pos-x",
                    "details": {
                        "simulation": True,
                        "symbol": "XAUUSD",
                        "action": "close_position",
                        "execution": {"run_id": run["id"], "agent_id": agent["id"]},
                    },
                },
            )
        )
    before = await revisions(f, agent["id"])
    await closed(f, account, agent["id"], new_id(), "40", operation_id=operation)
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert await runs_of(f, agent["id"], "broker_event") == [], "a second Run was started"
    seen: list[list[ModelMessage]] = []
    version = await memory_version(f, agent["id"])
    with patch.object(ctx.router, "complete", reviewer(version, seen, read_first=read_first)):
        await execute_run(ctx, load_tools(), 120, 8)
    assert any(CLOSED in m.content for messages in seen for m in messages)
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # read: nothing redirected
    path = "after a tool block" if read_first else "before its final reply"
    print("PASS the agent's own close reaches its still-executing Run", path, "; it reviews")


async def unread_notice(f: Fixture, account: str) -> None:
    agent = await f.agent("Gold quick")
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    await f.lease(run)
    async with f.runtime.db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id=new_id(),
                owner_id=f.owner,
                account_id=account,
                request_hash="h",
                request={"account_id": account, "symbol": "XAUUSD", "action": "close_position"},
                status="confirmed",
                result={
                    "status": "confirmed",
                    "details": {
                        "order_id": "close-quick",
                        "execution": {"run_id": run["id"], "agent_id": agent["id"]},
                    },
                },
            )
        )
    await closed(f, account, agent["id"], "close-quick", "3")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run["id"])
        assert row
        row.status = "completed"  # it ended before its next turn boundary
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (woken,) = await runs_of(f, agent["id"], "broker_event")
    assert CLOSED in woken.prompt
    assert await wake_for_closes(f.runtime.db, f.owner) == 0
    print("PASS a notice its Run never read becomes a broker_event Run, once")


async def paused_and_owner(f: Fixture, account: str) -> None:
    agent = await f.agent("Gold paused")
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent["id"])
        assert row
        row.paused = True
    await closed(f, account, agent["id"], "sl-paused", "5")
    await closed(f, account, None, "owner-terminal", "9")  # the owner's own trade
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (run,) = await runs_of(f, agent["id"], "broker_event")
    assert "You are paused" in run.prompt
    # A paused agent's own-trade wake is claimed and runs; its other work stays held.
    claimed: list[str] = []
    for _ in range(20):
        async with f.runtime.db.sessions() as session, session.begin():
            row = await claim_next(session, "close-worker", 120, "work")
        if row is None:
            break
        claimed.append(row.id)
    assert run.id in claimed, claimed
    print("PASS a paused agent is woken for its own trade; the owner's trade wakes nobody")


async def main() -> None:
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "close-source", "enabled": True},
            )
        )["id"]
        await stop_loss_hit(f, account)
        await own_close(f, account, read_first=True)
        await own_close(f, account, read_first=False)
        await unread_notice(f, account)
        await paused_and_owner(f, account)
        await many_woken(f, account)
        await deleted_owner(f, account)
        await busy_notices(f, account)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
