"""A deterministic watchdog that keeps the gateway honest without a model.

It reads liveness, the run queue, schedules and the trading journal, and it only ever
alerts the owner, quarantines a Run that keeps crashing its worker, or reports readiness.
It never sends, resends or decides a trade: an uncertain operation stays uncertain until
the broker or the owner settles it.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import IN_PROGRESS_STATUSES, UNRESOLVED_STATUSES
from lonora_db.attention import (
    raise_system_attention,
    settle_system_attention,
    withdraw_attention,
)
from lonora_db.client import Database
from lonora_db.item_failures import blocked, failure_code
from lonora_db.owner_actions import awaiting_owner_answer
from lonora_db.runs import MAX_RUN_RECOVERIES, aware, quarantine_run
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    GatewayRow,
    OwnerRow,
    RoutineRow,
    RunRow,
    ThreadRow,
    TradingJournalRow,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .health import HEARTBEAT_FRESH
from .liveness import Liveness

log = logging.getLogger("lonora.watchdog")

# An operation still uncertain after this long gets one owner attention item.
OPERATION_AGE = timedelta(minutes=15)
# A routine or timer wait this far past due means the scheduler is not keeping up.
OVERDUE_GRACE = timedelta(minutes=5)
SCHEDULER_STEPS = frozenset({"routines", "task_waits"})


async def operation_origin(
    session: AsyncSession, row: TradingJournalRow
) -> tuple[str | None, str | None]:
    """The agent and conversation of the Run that placed a journaled operation."""
    details: dict[str, Any] = (row.result or {}).get("details") or {}
    execution: dict[str, Any] = details.get("execution") or {}
    lease: dict[str, Any] = details.get("lease") or {}
    run_id = execution.get("run_id") or lease.get("run_id")
    run = await session.get(RunRow, str(run_id)) if run_id else None
    agent_id = execution.get("agent_id") or (run.agent_id if run else None)
    return (str(agent_id) if agent_id else None), (run.thread_id if run else None)


class Watchdog:
    def __init__(
        self,
        db: Database,
        liveness: Liveness,
        read_only_names: set[str],
        *,
        identity: str = "",
        operation_age: timedelta = OPERATION_AGE,
        overdue_grace: timedelta = OVERDUE_GRACE,
    ) -> None:
        self.db, self.liveness, self.read_only_names = db, liveness, read_only_names
        self.identity = identity
        self.operation_age, self.overdue_grace = operation_age, overdue_grace
        # One alert per stall episode; an episode ends when the condition clears. Each
        # item records its episode and gateway, so a restart can withdraw what it ended.
        self.episodes: dict[str, str] = {}

    async def tick(self) -> dict[str, int]:
        """Run every check; one failing check never skips the others."""
        checks: dict[str, Callable[[], Awaitable[int]]] = {
            "steps": self.stalled_steps,
            "runs": self.recovered_runs,
            "overdue": self.overdue_wakes,
            "operations": self.aging_operations,
            "ended": self.ended_episodes,
        }
        report: dict[str, int] = {}
        failure: Exception | None = None
        for name, check in checks.items():
            try:
                report[name] = await check()
            except Exception as error:
                failure = failure or error
                log.error("watchdog_check_failed check=%s code=%s", name, failure_code(error))
        if failure:
            raise failure
        return report

    async def owners(self) -> list[str]:
        async with self.db.sessions() as session:
            return list(await session.scalars(select(OwnerRow.id)))

    async def alert(self, code: str, subject: str, parameters: dict[str, object]) -> int:
        raised = 0
        for owner_id in await self.owners():
            async with self.db.sessions() as session, session.begin():
                raised += int(
                    await raise_system_attention(session, owner_id, code, subject, parameters)
                    is not None
                )
        return raised

    async def clear(self, code: str, subject: str) -> None:
        for owner_id in await self.owners():
            async with self.db.sessions() as session, session.begin():
                await settle_system_attention(session, owner_id, code, subject)

    async def stalled_steps(self) -> int:
        """A critical step that hangs or keeps failing reaches the owner once per episode."""
        now = utcnow()
        stalled = set(self.liveness.stalled(now))
        for name in [name for name in self.episodes if name.startswith("step:")]:
            if name.removeprefix("step:") not in stalled:
                log.info("step_recovered name=%s", name.removeprefix("step:"))
                await self.clear("gateway_degraded", self.episodes.pop(name))
        raised = 0
        for name in sorted(stalled):
            key = "step:" + name
            if key in self.episodes:
                continue
            self.episodes[key] = key + ":" + now.isoformat(timespec="minutes")
            log.error("step_stalled name=%s", name)
            raised += await self.alert(
                "gateway_degraded",
                self.episodes[key],
                {"reason_code": "step_stalled", "step": name, **self.episode(key)},
            )
        return raised

    def episode(self, key: str) -> dict[str, str]:
        return {"episode": self.episodes[key], "gateway": self.identity}

    async def ended_episodes(self) -> int:
        """Withdraw "running late" items no live watchdog stands behind any more.

        Episodes live in memory, so after a restart (often what cleared the stall) the
        earlier gateway's items would keep claiming the service is late. An item is
        withdrawn when its episode is not current here, or its gateway is gone.
        """
        current = set(self.episodes.values())
        now = utcnow()
        async with self.db.sessions() as session:
            items = list(
                await session.scalars(
                    select(AttentionRow)
                    .where(
                        AttentionRow.code == "gateway_degraded",
                        AttentionRow.status.in_(["pending", "ready"]),
                    )
                    .limit(100)
                )
            )
            live = {
                row.id
                for row in await session.scalars(select(GatewayRow))
                if row.state in {"running", "ready"}
                and now - aware(row.heartbeat_at) < HEARTBEAT_FRESH
            }
        ended = [
            item.id
            for item in items
            if (
                item.parameters.get("episode") not in current
                if item.parameters.get("gateway") == self.identity
                else item.parameters.get("gateway") not in live
            )
        ]
        withdrawn = 0
        for identifier in ended:
            async with self.db.sessions() as session, session.begin():
                row = await session.get(AttentionRow, identifier, with_for_update=True)
                withdrawn += int(row is not None and withdraw_attention(session, row))
        if withdrawn:
            log.info("degraded_items_withdrawn count=%s", withdrawn)
        return withdrawn

    async def recovered_runs(self) -> int:
        """Quarantine Runs that crashed their worker too often instead of re-leasing them.

        A Run with an unresolved financial operation is held, not failed: the journal
        reconciler settles that operation first, and the owner already gets one item per
        aging operation.
        """
        async with self.db.sessions() as session:
            identifiers = list(
                await session.scalars(
                    select(RunRow.id)
                    .where(
                        RunRow.status.in_(["leased", "running"]),
                        RunRow.lease_expires_at <= utcnow(),
                        RunRow.recovery_count >= MAX_RUN_RECOVERIES,
                    )
                    .order_by(RunRow.updated_at)
                    .limit(20)
                )
            )
        quarantined = 0
        for identifier in identifiers:
            try:
                quarantined += int(await self.quarantine(identifier))
            except Exception as error:
                log.error("run_quarantine_failed code=%s", failure_code(error))
        return quarantined

    async def quarantine(self, identifier: str) -> bool:
        async with self.db.sessions() as session, session.begin():
            outcome = await quarantine_run(session, identifier, self.read_only_names)
            row = await session.get(RunRow, identifier)
            thread = await session.get(ThreadRow, row.thread_id) if row else None
        if outcome == "held":
            log.warning("run_quarantine_held reason=unresolved_financial")
            return False
        if outcome != "failed" or row is None or thread is None:
            return False
        log.error("run_quarantined code=run_recovery_limit")
        if not row.model_metadata.get("task_id"):
            # A Task's own failure (task_review) already reaches the owner.
            async with self.db.sessions() as session, session.begin():
                await raise_system_attention(
                    session,
                    thread.owner_id,
                    "run_quarantined",
                    identifier,
                    {"run_id": identifier},
                    # The item opens the agent and conversation where the work stopped.
                    agent_id=row.agent_id,
                    thread_id=row.thread_id,
                )
        from lonora_agent.collaboration.outcome_return import return_outcome

        # A failure here is repaired by the outcomes step, which returns failed Runs.
        await return_outcome(self.db, identifier)
        return True

    async def overdue_wakes(self) -> int:
        """Routines and timer waits far past due mean the scheduler is not keeping up."""
        limit = utcnow() - self.overdue_grace
        wait = RunRow.execution_state["environment"]["wait"]
        async with self.db.sessions() as session:
            routines = await session.scalar(
                select(func.count(RoutineRow.id))
                .join(AgentRow, AgentRow.id == RoutineRow.agent_id)
                .where(
                    RoutineRow.enabled.is_(True),
                    RoutineRow.next_run_at < limit,
                    AgentRow.paused.is_(False),
                    ~blocked("routine", RoutineRow.id),
                )
            )
            waits = await session.scalar(
                select(func.count(RunRow.id)).where(
                    and_(
                        RunRow.status == "waiting_takeover",
                        wait["kind"].as_string() == "timer",
                        wait["due_at"].as_string() < limit.isoformat(),
                        ~blocked("task_wait", RunRow.id),
                    )
                )
            )
        overdue = int(routines or 0) + int(waits or 0)
        if not overdue:
            if "overdue" in self.episodes:
                await self.clear("gateway_degraded", self.episodes.pop("overdue"))
            return 0
        if "overdue" in self.episodes or any(
            "step:" + name in self.episodes for name in SCHEDULER_STEPS
        ):
            # Already reported, or reported as the stalled scheduler step itself.
            return 0
        self.episodes["overdue"] = "overdue:" + utcnow().isoformat(timespec="minutes")
        log.error("wakes_overdue count=%s", overdue)
        return await self.alert(
            "gateway_degraded",
            self.episodes["overdue"],
            {"reason_code": "wakes_overdue", "count": overdue, **self.episode("overdue")},
        )

    async def aging_operations(self) -> int:
        """One owner attention item per financial operation still uncertain after a while."""
        cutoff = utcnow() - self.operation_age
        async with self.db.sessions() as session:
            rows = list(
                await session.scalars(
                    select(TradingJournalRow)
                    .where(
                        TradingJournalRow.execution_mode == "live",
                        TradingJournalRow.status.in_(
                            sorted(IN_PROGRESS_STATUSES | UNRESOLVED_STATUSES)
                        ),
                        func.coalesce(TradingJournalRow.submitted_at, TradingJournalRow.updated_at)
                        < cutoff,
                    )
                    .order_by(TradingJournalRow.updated_at)
                    .limit(50)
                )
            )
        await self.settled_operations()
        raised = 0
        for row in rows:
            async with self.db.sessions() as session, session.begin():
                if await awaiting_owner_answer(session, row.owner_id, row.operation_id):
                    continue  # Its resolve card or uncertain-trade alert already asks.
                agent_id, thread_id = await operation_origin(session, row)
                raised += int(
                    await raise_system_attention(
                        session,
                        row.owner_id,
                        "operation_unresolved",
                        row.operation_id,
                        {
                            "operation_id": row.operation_id,
                            "account_id": row.account_id,
                            "symbol": row.request.get("symbol"),
                        },
                        # The item opens the agent and conversation that placed the trade.
                        agent_id=agent_id,
                        thread_id=thread_id,
                    )
                    is not None
                )
        return raised

    async def settled_operations(self) -> None:
        """Withdraw an unread item once the broker or the owner has settled its operation."""
        async with self.db.sessions() as session:
            items = list(
                await session.scalars(
                    select(AttentionRow)
                    .where(
                        AttentionRow.code == "operation_unresolved",
                        AttentionRow.status.in_(["pending", "ready"]),
                    )
                    .limit(100)
                )
            )
            settled = [
                item
                for item in items
                if (
                    journal := await session.get(
                        TradingJournalRow, str(item.parameters.get("operation_id", ""))
                    )
                )
                is None
                or journal.status not in IN_PROGRESS_STATUSES | UNRESOLVED_STATUSES
            ]
        for item in settled:
            async with self.db.sessions() as session, session.begin():
                await settle_system_attention(
                    session,
                    item.owner_id,
                    "operation_unresolved",
                    str(item.parameters.get("operation_id", "")),
                )
