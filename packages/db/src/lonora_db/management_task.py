"""The continuous account-management task of Full mode (mandate 4.5, 14.3.3).

An agent in Full that is not paused has exactly one continuous Task, keyed by the agent
(its kickoff Run carries ``account_management_id`` = the agent's id, the recovery path
of ``is_continuous_task``). It is bound to no account: every wake reads the accounts
connected at that moment, so a newly connected account joins it and a disconnected one
leaves it. Its Runs are ordinary Runs of the agent under the agent's mode.

- ``ensure_management_task`` starts the task when the agent is in Full and not paused;
  otherwise it does nothing. It is the only account-management task (4.5.1).
- ``end_management_task`` ends it: on the switch to Ask, a pause or a delete. Ending keeps what the agent set up (``close_task``): its Runs
  go on outside the task with their Trade Approval cards still decidable, its watches
  move to its conversation, a pending timer becomes a one-shot routine there, and its
  routines are untouched; the agent keeps managing its positions in Ask.

Both are called inside the caller's transaction, under the agent's authority lock.
"""

from typing import Any

from lonora_bus.attention import attention_text
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .authority_lock import authority_lock
from .conversation_locale import conversation_locale
from .events import emit
from .schema import AgentRow, MarketWatchRow, RunRow, TicketRow
from .tasks import create_task, save_task, task_state
from .threads import conversation_thread

MARKER = "account_management_agent"
TERMINAL = frozenset({"completed", "cancelled"})
DESCRIPTION = (
    "You are in Full mode: you manage every connected trading account on your own and "
    "report afterwards. This continuous task is how that work goes on while the owner is "
    "away. On each wake read the connected accounts and the broker's actual positions, "
    "orders and quotes, assess your open positions and the markets of your method, and "
    "decide: enter, add, reduce, move stops, exit, or wait. Not trading is a decision. "
    "Use the journaled trade tools and verify every broker effect before you report it. "
    "Inspect your existing watches and schedules before creating any. Before yielding, "
    "persist a real wait (task_wait) on a watch, a broker recovery or a justified timer, "
    "so this same work resumes with fresh evidence, and post a short update only when "
    "there is an actual result or a changed blocker."
)


async def open_management_tasks(
    session: AsyncSession, owner_id: str, agent_id: str
) -> list[TicketRow]:
    """The agent's mode tasks that are not cancelled or completed, newest first: a failed
    one is still open, because recovery can resume it."""
    rows = await session.scalars(
        select(TicketRow)
        .where(
            TicketRow.owner_id == owner_id,
            TicketRow.agent_id == agent_id,
            TicketRow.payload[MARKER].as_string() == agent_id,
        )
        .order_by(TicketRow.created_at.desc())
        .execution_options(populate_existing=True)
    )
    return [row for row in rows if task_state(row).status not in TERMINAL]


async def live_management_task(
    session: AsyncSession, owner_id: str, agent_id: str
) -> TicketRow | None:
    """The agent's one mode task: open, not asked to end, and not failed for good (a
    failed one with a retry due resumes by itself). It may be paused by the owner."""
    for row in await open_management_tasks(session, owner_id, agent_id):
        if task_live(row):
            return row
    return None


def task_live(row: TicketRow) -> bool:
    state = task_state(row)
    if state.status in TERMINAL or state.control_requested in {"cancel", "complete"}:
        return False
    return state.status != "failed" or bool(state.failure and state.failure.next_retry_at)


async def ensure_management_task(
    session: AsyncSession, owner_id: str, agent_id: str
) -> TicketRow | None:
    """Start the agent's one continuous task when it should run; return it, or None."""
    await authority_lock(session, agent_id)
    agent = await session.get(AgentRow, agent_id, populate_existing=True)
    if agent is None or agent.owner_id != owner_id:
        return None
    if agent.trading_mode != "full" or agent.paused:
        return None
    existing = await live_management_task(session, owner_id, agent_id)
    if existing is not None:
        return existing
    # A mode task that failed for good, or that is ending, is closed before the new one,
    # so the agent never has two.
    for row in await open_management_tasks(session, owner_id, agent_id):
        await close_task(session, row)
    thread = await conversation_thread(session, owner_id, agent_id)
    locale = await conversation_locale(session, owner_id, thread.id)
    task = await create_task(
        session,
        owner_id,
        agent_id,
        thread.id,
        TaskCreate(
            title=attention_text("account_management_task", locale),
            completion_mode="continuous",
            description=DESCRIPTION,
        ),
    )
    task.payload = {**task.payload, MARKER: agent_id}
    run = await session.get(RunRow, task.payload["run_id"])
    assert run is not None
    run.model_metadata = {
        **run.model_metadata,
        "account_management_id": agent_id,
        "reply_locale": locale,
    }
    await session.flush()
    return task


async def end_management_task(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """End every open mode task of the agent (a failed one too, so recovery cannot
    resume it), in the caller's transaction; idempotent. See ``close_task`` for what happens to its Runs, cards, watches and timer."""
    await authority_lock(session, agent_id)
    for row in await open_management_tasks(session, owner_id, agent_id):
        await close_task(session, row)


async def close_task(session: AsyncSession, found: TicketRow) -> None:
    """Close one mode task. Nothing the agent set up is lost (4.5.3):

    - A Run of the task that is working, waiting for the owner (a question or a Trade
      Approval card), queued after a wake, or failed leaves the task and goes on as an
      ordinary Run of the agent: it keeps its cards, which stay decidable and end only as
      10.3.1.3 says, its in-flight request is decided under the agent's mode, and a watch
      it creates from now on belongs to the agent's conversation. A paused agent's Runs
      are held by the worker until the owner resumes it.
    - The kickoff Run that never started is cancelled; nothing of it exists yet.
    - A Run suspended on its own ``task_wait`` (or held by the owner's pause of the task)
      is cancelled, since only the task could resume it: a timer becomes a one-shot
      routine of the agent in its conversation at the same time (held while the agent is
      paused); a watch stays, moved to the conversation, and wakes the agent there.
    - A task the owner already asked to cancel or complete is left to end that way.
    - The task's watches move to the agent's conversation and keep watching.

    Locks follow the Task order elsewhere: the Runs, then the Task."""
    runs = list(
        await session.scalars(
            select(RunRow)
            .where(
                RunRow.thread_id == found.thread_id,
                RunRow.agent_id == found.agent_id,
                RunRow.status.in_(
                    [
                        "queued",
                        "leased",
                        "running",
                        "waiting_input",
                        "waiting_takeover",
                        "failed",
                    ]
                ),
            )
            .order_by(RunRow.created_at)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    task = await session.get(TicketRow, found.id, with_for_update=True, populate_existing=True)
    if task is None or task_state(task).status in TERMINAL:
        return
    if task_state(task).control_requested in {"cancel", "complete"}:
        return  # The owner already ended it; its Run stops at its checkpoint.
    for run in runs:
        if run.model_metadata.get("task_id") != task.id:
            continue
        wait = run.execution_state.get("environment", {}).get("wait")
        if run.status == "waiting_takeover":
            # Suspended on its own wait, or held by the owner's pause of the task: only
            # the task could resume it.
            if wait and wait.get("kind") == "timer" and wait.get("due_at"):
                await keep_timer(session, task, str(wait["due_at"]))
            run.status = "cancelled"
            run.updated_at = utcnow()
        elif run.status == "queued" and not started(run):
            run.status = "cancelled"
            run.updated_at = utcnow()
        else:
            detach(run)
    await keep_watches(session, task)
    state = task_state(task)
    state.status, state.phase, state.control_requested = "cancelled", "cancelled", None
    state.waiting_reason = None
    if state.failure:
        state.failure.next_retry_at = None
    save_task(session, task, state)


def started(run: RunRow) -> bool:
    """Whether the Run has done anything: model turns, or a wake it was resumed for."""
    state = run.execution_state
    return bool(state.get("messages") or state.get("environment", {}).get("last_wake"))


def detach(run: RunRow) -> None:
    """The Run leaves the task and goes on as an ordinary Run of the agent."""
    run.model_metadata = {
        key: value
        for key, value in run.model_metadata.items()
        if key not in {"task_id", "ticket_id", "account_management_id"}
    }
    run.updated_at = utcnow()


TIMER_PROMPT = (
    "A timer you set while running your continuous account-management task is due "
    "(set for {due_at}). That task has ended; you work under your current trading mode. "
    "Re-check your open positions, pending orders and the market, then decide."
)


async def keep_timer(session: AsyncSession, task: TicketRow, due_at: str) -> None:
    """The agent's pending timer outlives the task: the same wake at the same time, in
    the agent's conversation, as a one-shot routine (routines are held while paused)."""
    from datetime import datetime

    from .schema import RoutineRow

    thread = await conversation_thread(session, task.owner_id, task.agent_id or "")
    when = datetime.fromisoformat(due_at)
    session.add(
        RoutineRow(
            owner_id=task.owner_id,
            agent_id=task.agent_id,
            thread_id=thread.id,
            title=task.payload.get("title"),
            prompt=TIMER_PROMPT.format(due_at=when.isoformat()),
            run_at=when,
            next_run_at=when,
        )
    )
    await session.flush()


async def keep_watches(session: AsyncSession, task: TicketRow) -> None:
    """The agent's own watches outlive the task (4.5.3): they leave the task's work lane
    for the agent's conversation, where a trigger wakes the agent as any watch does."""
    thread = await conversation_thread(session, task.owner_id, task.agent_id or "")
    for watch in await session.scalars(
        select(MarketWatchRow)
        .where(
            MarketWatchRow.owner_id == task.owner_id,
            MarketWatchRow.state["task_id"].as_string() == task.id,
        )
        .order_by(MarketWatchRow.id)
        .with_for_update()
    ):
        state: dict[str, Any] = {
            key: value
            for key, value in watch.state.items()
            if key not in {"task_id", "task_run_id"}
        }
        watch.state, watch.thread_id = state, thread.id
        watch.version += 1
        watch.updated_at = utcnow()
        emit(
            session,
            watch.owner_id,
            "market_watches.updated",
            agent_id=watch.agent_id,
            thread_id=watch.thread_id,
            payload={"id": watch.id, "version": watch.version},
        )
