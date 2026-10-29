"""Persistent task wait/wake uses actual tools, broker/watch state and resident scheduler."""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_db.runs import claim_next
from lonora_db.schema import MarketWatchRow, RunRow
from lonora_db.task_wait import resume_ready_waits
from lonora_db.tasks import control_task, create_task, get_task, snapshot
from lonora_market.watchers import check_watches
from lonora_tools.loader import load_tools
from lonora_trading.broker_recovery import reconcile_broker_account
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    try:
        agent = await f.agent("Durable external wait")
        origin = await f.conversation(agent)
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "wait-source", "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {"snapshot": {"currency": "USD", "balance": "10000", "instruments": [], "quotes": {}}},
        )
        for kind in ("watch", "timer", "broker_recovery"):
            async with f.runtime.db.sessions() as session, session.begin():
                task = await create_task(
                    session,
                    f.owner,
                    agent["id"],
                    origin["id"],
                    TaskCreate(title="Wait for " + kind),
                )
                run = await session.get(RunRow, task.payload["run_id"])
                assert run
                data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
            ctx = await f.lease(data)
            phase, watch_id = 0, ""

            async def complete(
                _: Any, messages: list[ModelMessage], tools: Any, kind: str = kind, **kwargs: Any
            ):
                nonlocal phase, watch_id
                phase += 1
                if phase == 1 and kind == "watch":
                    return ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="create-watch",
                                name="watch_create",
                                arguments={
                                    "account_id": account,
                                    "symbol": "US500.cash",
                                    "kind": "price",
                                    "condition": "above",
                                    "level": "100",
                                    "prompt": "Revalidate after trigger",
                                },
                            )
                        ]
                    ), ModelSelection(provider="openai", model="scripted-wait")
                if (phase == 1 and kind != "watch") or (phase == 2 and kind == "watch"):
                    if kind == "watch":
                        observation = next(
                            message for message in reversed(messages) if message.role == "tool"
                        )
                        watch_id = json.loads(observation.content)["id"]
                    return ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="durable-wait",
                                name="task_wait",
                                arguments={
                                    "kind": kind,
                                    "source_id": watch_id
                                    if kind == "watch"
                                    else account
                                    if kind == "broker_recovery"
                                    else None,
                                    "seconds": 60,
                                },
                            )
                        ]
                    ), ModelSelection(provider="openai", model="scripted-wait")
                assert any("<runtime_wake>" in message.content for message in messages)
                return ModelReply(
                    text="Verified external wake; continuing the same task."
                ), ModelSelection(provider="openai", model="scripted-wait")

            with patch.object(ctx.router, "complete", complete):
                await execute_run(ctx, load_tools(), 120, 8)
                async with f.runtime.db.sessions() as session:
                    current = await session.get(RunRow, ctx.lease.run_id)
                    state = await snapshot(session, await get_task(session, f.owner, task.id))
                    assert (
                        current
                        and current.status == "waiting_takeover"
                        and state["status"] == "waiting"
                    )
                    assert state["waiting_reason"] == "external_" + kind
                # Recovered worker after checkpoint/suspend crash must not ask the model or execute again.
                recovered = await f.lease(data)
                await execute_run(recovered, load_tools(), 120, 8)
                assert phase == (2 if kind == "watch" else 1)
                assert await resume_ready_waits(f.runtime.db) == 0
                if kind == "timer":
                    async with f.runtime.db.sessions() as session, session.begin():
                        current = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
                        assert current
                        env = dict(current.execution_state["environment"])
                        env["wait"] = {
                            **env["wait"],
                            "due_at": (utcnow() - timedelta(seconds=1)).isoformat(),
                        }
                        current.execution_state = {**current.execution_state, "environment": env}
                elif kind == "watch":
                    assert (
                        await check_watches(
                            f.runtime.db,
                            ctx.brokers,
                            price_update=Quote(
                                symbol="US500.cash",
                                bid=Decimal("101"),
                                ask=Decimal("102"),
                                observed_at=utcnow(),
                                source="explicit-wait-fixture",
                            ),
                            connection_id=account,
                            owner_id=f.owner,
                        )
                        == 1
                    )
                    async with f.runtime.db.sessions() as session:
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(RunRow)
                                .where(RunRow.thread_id == ctx.thread_id)
                            )
                            == 1
                        )
                        watch = await session.get(MarketWatchRow, watch_id)
                        assert watch and watch.state["last_triggered"]
                else:
                    health = await reconcile_broker_account(
                        f.runtime.db, ctx.brokers, f.owner, account
                    )
                    assert health and health.status == "connected", (
                        health.reason_code if health else "no-result"
                    )
                woken = await asyncio.gather(
                    resume_ready_waits(f.runtime.db), resume_ready_waits(f.runtime.db)
                )
                assert sum(woken) == 1, (kind, woken)
                assert await resume_ready_waits(f.runtime.db) == 0
                async with f.runtime.db.sessions() as session, session.begin():
                    claimed = await claim_next(session, "wake-worker", 120, "work")
                    assert claimed and claimed.id == ctx.lease.run_id
                ctx = await f.lease(data)
                await execute_run(ctx, load_tools(), 120, 8)
            async with f.runtime.db.sessions() as session:
                state = await snapshot(session, await get_task(session, f.owner, task.id))
                current = await session.get(RunRow, ctx.lease.run_id)
                assert current and current.status == "completed" and state["status"] == "completed"
                assert state["id"] == task.id
            print("PASS actual same Task/Run checkpoint resumes exactly once after", kind)

        # Owner cancellation beats a ready external wait.
        async with f.runtime.db.sessions() as session, session.begin():
            task = await create_task(
                session, f.owner, agent["id"], origin["id"], TaskCreate(title="Owner stops wait")
            )
            run = await session.get(RunRow, task.payload["run_id"])
            assert run
            data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
        ctx = await f.lease(data)

        async def wait_only(*args: Any, **kwargs: Any):
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="wait", name="task_wait", arguments={"kind": "timer", "seconds": 60}
                    )
                ]
            ), ModelSelection(provider="openai", model="scripted-wait")

        with patch.object(ctx.router, "complete", wait_only):
            await execute_run(ctx, load_tools(), 120, 8)
        async with f.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, f.owner, task.id)
            await control_task(
                session,
                f.owner,
                TaskControl(task_id=task.id, expected_version=row.version, action="cancel"),
                agent_id=agent["id"],
            )
        assert await resume_ready_waits(f.runtime.db) == 0
        print("PASS cancellation prevents external wake from reviving Task")
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
