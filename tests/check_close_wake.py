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
from lonora_db.schema import (
    AgentRow,
    ClosedTradeRow,
    MemoryRevisionRow,
    RunRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from lonora_trading.close_wake import wake_for_closes
from sqlalchemy import func, select

SELECTION = ModelSelection(provider="openai", model="scripted-close")
CLOSED = "A trade you owned has closed at the broker"


async def closed(
    f: Fixture, account: str, agent_id: str | None, closing_order: str, pnl: str | None
) -> str:
    """A ledger row as W-LEDGER writes it: the trade's broker deals, its P&L and owner."""
    trade = new_id()
    now = utcnow()
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
                    {"id": "deal-out-" + trade[:8], "orderId": closing_order},
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


def reviewer(version: int, seen: list[list[ModelMessage]]) -> Any:
    """A model that answers the close text with a self-review in its memory."""

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
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
        return ModelReply(text="Reviewed."), SELECTION

    return complete


async def memory_version(f: Fixture, agent_id: str) -> int:
    async with f.runtime.db.sessions() as session:
        return (await read_memory(session, f.owner, agent_id)).version


async def stop_loss_hit(f: Fixture, account: str) -> None:
    agent = await f.agent("Gold stop")
    before = await revisions(f, agent["id"])
    trade = await closed(f, account, agent["id"], "sl-order", "-12.5")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # once per trade
    (run,) = await runs_of(f, agent["id"], "broker_event")
    assert CLOSED in run.prompt and '"realized_pnl": "-12.5"' in run.prompt
    assert '"label": "secure_then_add"' in run.prompt and trade[:8] in run.prompt
    assert run.model_metadata.get("authority") != "observe_only"
    seen: list[list[ModelMessage]] = []
    data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    ctx = await f.lease(data)
    with patch.object(ctx.router, "complete", reviewer(await memory_version(f, agent["id"]), seen)):
        await execute_run(ctx, load_tools(), 120, 8)
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    print("PASS a stop-loss hit wakes the position's owner, which writes a self-review")


async def own_close(f: Fixture, account: str) -> None:
    agent = await f.agent("Gold manager")
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    ctx = await f.lease(run)  # the closing Run is executing
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
                        "order_id": "close-own",
                        "execution": {"run_id": run["id"], "agent_id": agent["id"]},
                    },
                },
            )
        )
    before = await revisions(f, agent["id"])
    await closed(f, account, agent["id"], "close-own", "40")
    assert await wake_for_closes(f.runtime.db, f.owner) == 1
    assert await runs_of(f, agent["id"], "broker_event") == [], "a second Run was started"
    seen: list[list[ModelMessage]] = []
    with patch.object(ctx.router, "complete", reviewer(await memory_version(f, agent["id"]), seen)):
        await execute_run(ctx, load_tools(), 120, 8)
    assert any(CLOSED in m.content for messages in seen for m in messages)
    assert await revisions(f, agent["id"]) == before + 1, "no self-review was written"
    assert await wake_for_closes(f.runtime.db, f.owner) == 0  # read: nothing redirected
    print("PASS the agent's own close reaches its still-executing Run, which writes a review")


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
    assert "You are paused" in run.prompt and run.model_metadata.get("authority") is None
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
        await own_close(f, account)
        await unread_notice(f, account)
        await paused_and_owner(f, account)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
