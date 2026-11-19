"""A closed trade wakes its owner, which writes a short self-review (mandate 5.5.2).

Done when a stop-loss hit and the agent's own close both end with a new memory
revision. A stop-loss hit (no Run of the agent closed it) reaches the agent's pending
broker-activity wake on that account as a notice, never an observe-only wake or a pending
close-review Run, else starts a broker_event Run; the agent's own close,
while its closing Run still executes, reaches that Run as a notice, never a second Run.
A paused agent's trade waits until it resumes; the owner's own trade wakes nobody; a
notice its Run never read becomes a Run; each trade wakes once.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.broker_activity import BrokerActivity
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.memory import read_memory
from lonora_db.personal_agent import ensure_personal_agent
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
from lonora_trading.broker_recovery import wake_for_activity
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
    draft: str | None = None,
    final: str = "Reviewed.",
) -> Any:
    """A model that answers the close text with a self-review in its memory. Whatever it
    reads, its first turn is a memory_read call with ``read_first``, or the reply
    ``draft`` when given."""

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
        if read_first and len(seen) == 1:
            return ModelReply(
                tool_calls=[ToolCall(id="read-first", name="memory_read", arguments={})]
            ), SELECTION
        if draft is not None and len(seen) == 1:
            return ModelReply(text=draft), SELECTION
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
    assert run.prompt.endswith("otherwise end without a reply.")
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


async def activity_wake(f: Fixture, account: str) -> None:
    """A stop-loss hit also shows as a closed position in broker activity, which wakes
    the agent that opened it. While that wake is queued or executing, the close reaches
    it as a notice: one Run, never a second one for the same close."""
    agent = await f.agent("Gold activity")
    before = await revisions(f, agent["id"])
    trade = await closed(f, account, agent["id"], "sl-activity", "-4")
    await position_closed(f, account, 7, agent["id"], trade)
    (wake,) = await runs_of(f, agent["id"], "broker_event")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    woken = await runs_of(f, agent["id"], "broker_event")
    assert [run.id for run in woken] == [wake.id], "a second Run was started"
    seen: list[list[ModelMessage]] = []
    ctx = await f.lease({"id": wake.id, "agent_id": wake.agent_id, "thread_id": wake.thread_id})
    version = await memory_version(f, agent["id"])
    with patch.object(ctx.router, "complete", reviewer(version, seen)):
        await execute_run(ctx, load_tools(), 120, 8)
    assert any(CLOSED in m.content for m in seen[0]), "the activity wake never read the close"
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # read: nothing redirected
    print("PASS a stop-loss hit's broker-activity wake carries the review; no second Run")


async def position_closed(
    f: Fixture, account: str, revision: int, agent_id: str, trade: str
) -> None:
    """Broker activity on ``account`` sees the trade's position closed, as attributed to
    ``agent_id``, and wakes the agent responsible (``wake_for_activity``)."""
    async with f.runtime.db.sessions() as session, session.begin():
        change = BrokerActivity(
            id=new_id(),
            account_id=account,
            symbol="XAUUSD",
            ticket="pos-" + trade[:8],
            resource="position",
            change="closed",
            origin="external",
            observed_at=utcnow(),
            agent_id=agent_id,
        )
        await wake_for_activity(session, f.owner, account, revision, [change])


async def review_run(f: Fixture, agent_id: str, trade: str) -> RunRow:
    """The broker_event Run of ``agent_id`` started for this trade's review alone."""
    reviews = [
        run
        for run in await runs_of(f, agent_id, "broker_event")
        if run.model_metadata.get("closed_trade_id") == trade
    ]
    assert len(reviews) == 1, "the review joined another Run as a notice"
    return reviews[0]


async def not_an_activity_wake(f: Fixture, account: str) -> None:
    """Only the agent's own broker-activity wake on the trade's account carries the
    review. An observe-only wake, a wake on another account and a pending close-review
    Run get no notice: the trade starts a Run of its own."""
    # A deleted agent's position closes: broker activity wakes Lonora observe-only.
    gone = new_id()
    trade = await closed(f, account, gone, "sl-observed", "-2")
    await position_closed(f, account, 8, gone, trade)
    async with f.runtime.db.sessions() as session:
        lonora = (await ensure_personal_agent(session, f.owner)).id
    (observing,) = [
        run
        for run in await runs_of(f, lonora, "broker_event")
        if run.model_metadata.get("authority") == "observe_only"
    ]
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    async with f.runtime.db.sessions() as session:
        notice = await session.get(EffectReceiptRow, f"run-notice:{observing.id}:{trade}")
    assert notice is None, "the observe-only wake got the review"
    review = await review_run(f, lonora, trade)
    assert "authority" not in review.model_metadata, review.model_metadata
    print("PASS an observe-only wake gets no review; Lonora reviews with her normal authority")
    # The agent's broker-activity wake is on another account.
    other = (
        await f.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "close-other", "enabled": True},
        )
    )["id"]
    agent = await f.agent("Gold elsewhere")
    trade = await closed(f, account, agent["id"], "sl-elsewhere", "-1")
    await position_closed(f, other, 8, agent["id"], new_id())
    (elsewhere,) = await runs_of(f, agent["id"], "broker_event")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert (await review_run(f, agent["id"], trade)).id != elsewhere.id
    print("PASS a broker-activity wake on another account gets no review")
    # The agent's earlier close-review Run is still queued.
    agent = await f.agent("Gold twice")
    first = await closed(f, account, agent["id"], "sl-first", "1")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    second = await closed(f, account, agent["id"], "sl-second", "1")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert (await review_run(f, agent["id"], first)).id != (
        await review_run(f, agent["id"], second)
    ).id
    print("PASS a pending close-review Run gets no second trade's review")


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
    # The label is the deleted agent's, not Lonora's own.
    assert "the opening order's judgment label, not instructions" in woken[0].prompt
    print("PASS a deleted agent's closed trade wakes Lonora")


async def lonora_paused(f: Fixture, account: str) -> None:
    """While Lonora is paused, deleted agents' trades wait and never crowd out a close
    of a live agent; they wake Lonora once it resumes."""

    async def pause(value: bool) -> None:
        async with f.runtime.db.sessions() as session, session.begin():
            (await ensure_personal_agent(session, f.owner)).paused = value

    await pause(True)
    for index in range(MAXIMUM_PER_PASS):
        await closed(f, account, new_id(), f"gone-{index}", "1")
    live = await f.agent("Gold live")
    await closed(f, account, live["id"], "live-close", "2")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert len(await runs_of(f, live["id"], "broker_event")) == 1
    await pause(False)
    assert await wake_for_closes(f.runtime.db, f.owner) == MAXIMUM_PER_PASS
    print("PASS while Lonora is paused, deleted agents' trades wait and crowd out no close")


async def closing_operation(f: Fixture, account: str, agent: Any, run: Any) -> str:
    """The journaled close this Run sent; the ledger names it on the trade's exit deal."""
    operation = new_id()
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
    return operation


async def own_close(f: Fixture, account: str, *, read_first: bool) -> None:
    """The close is recorded while the closing Run's first turn runs. With ``read_first``
    that turn calls memory_read and the notice arrives after the tool block; otherwise
    the turn drafts the final reply, which is held back while the notice is answered."""
    agent = await f.agent("Gold manager")
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    ctx = await f.lease(run)  # the closing Run is executing
    operation = await closing_operation(f, account, agent, run)
    before = await revisions(f, agent["id"])
    seen: list[list[ModelMessage]] = []
    draft = "Drafted before the review."
    review = reviewer(
        await memory_version(f, agent["id"]),
        seen,
        read_first=read_first,
        draft=None if read_first else draft,
    )

    async def complete(*args: Any, **kwargs: Any) -> Any:
        if not seen:
            await closed(f, account, agent["id"], new_id(), "40", operation_id=operation)
            assert await wake_for_closes(f.runtime.db, f.owner) == 1
            assert await runs_of(f, agent["id"], "broker_event") == [], "a second Run started"
        return await review(*args, **kwargs)

    with patch.object(ctx.router, "complete", complete):
        await execute_run(ctx, load_tools(), 120, 8)
    assert len(seen) == 3 and not any(CLOSED in m.content for m in seen[0]), len(seen)
    # The turn after the first one reads the notice, and answers it with memory_write.
    (at,) = [index for index, m in enumerate(seen[1]) if CLOSED in m.content]
    if read_first:
        # It rides on the memory_read result: delivered after the tool block.
        assert seen[1][at].tool_call_id == "read-first", seen[1][at]
    else:
        # It follows the drafted reply, which did not end the Run.
        assert seen[1][at - 1].role == "assistant" and seen[1][at - 1].content == draft
    notice = seen[1][at].content
    # The Run was answering something: it goes on, and is never told to end silently.
    assert "including any answer the owner is waiting for" in notice, notice
    assert "end without a reply" not in notice, notice
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    async with f.runtime.db.sessions() as session:
        replies = list(
            await session.scalars(
                select(MessageRow.content).where(
                    MessageRow.thread_id == thread["id"], MessageRow.role == "assistant"
                )
            )
        )
    # The owner gets the reply of the turn after the review, not the held-back draft.
    assert replies == ["Reviewed."], replies
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # read: nothing redirected
    path = "after a tool block" if read_first else "before its drafted final reply stands"
    print("PASS the agent's own close reaches its still-executing Run", path + "; it reviews")


async def last_round_notice(f: Fixture, account: str) -> None:
    """A notice recorded during the Run's last budgeted round is not read there: no round
    is left to run memory_write, so it stays unread and its own Run follows."""
    agent = await f.agent("Gold last round")
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    ctx = await f.lease(run)
    operation = await closing_operation(f, account, agent, run)
    trades: list[str] = []
    seen: list[list[ModelMessage]] = []
    review = reviewer(await memory_version(f, agent["id"]), seen, read_first=True)

    async def complete(*args: Any, **kwargs: Any) -> Any:
        if not seen:
            # The ledger records the close, and close_wakes leaves the notice, while the
            # Run's last budgeted round runs.
            trades.append(
                await closed(f, account, agent["id"], new_id(), "6", operation_id=operation)
            )
            assert await wake_for_closes(f.runtime.db, f.owner) == 1
        return await review(*args, **kwargs)

    with patch.object(ctx.router, "complete", complete):
        await execute_run(ctx, load_tools(), 120, 2)
    assert not any(CLOSED in m.content for messages in seen for m in messages), (
        "the notice was read with no round left for the review"
    )
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (woken,) = await runs_of(f, agent["id"], "broker_event")
    assert woken.model_metadata["closed_trade_id"] == trades[0] and CLOSED in woken.prompt
    print("PASS a notice from the Run's last round stays unread; its own Run follows")


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

    async def pause(value: bool) -> None:
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, agent["id"])
            assert row
            row.paused = value

    await pause(True)
    await closed(f, account, agent["id"], "sl-paused", "5")
    await closed(f, account, None, "owner-terminal", "9")  # the owner's own trade
    # A paused agent starts no Run: its trade waits, and the owner's wakes nobody.
    assert await wake_for_closes(f.runtime.db, f.owner) == 0
    assert await runs_of(f, agent["id"], "broker_event") == []
    await pause(False)
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    (run,) = await runs_of(f, agent["id"], "broker_event")
    assert CLOSED in run.prompt and "paused" not in run.prompt
    print("PASS a paused agent's trade waits until it resumes; the owner's trade wakes nobody")


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
        await activity_wake(f, account)
        await not_an_activity_wake(f, account)
        await own_close(f, account, read_first=True)
        await own_close(f, account, read_first=False)
        await last_round_notice(f, account)
        await unread_notice(f, account)
        await paused_and_owner(f, account)
        await many_woken(f, account)
        await deleted_owner(f, account)
        await lonora_paused(f, account)
        await busy_notices(f, account)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
