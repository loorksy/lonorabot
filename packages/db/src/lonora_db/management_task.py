"""The continuous account-management task of Full mode (mandate 4.5, 14.3.3).

An agent in Full that is not paused runs one continuous Task, keyed by the agent (its
kickoff Run carries ``account_management_id`` = the agent's id, the recovery path of
``is_continuous_task``), except while a signed grant's own Task drives the account, or
after the owner cancelled or completed it or it failed for good. It is bound to no
account: every wake reads the accounts connected at that moment, so a newly connected
account joins it and a disconnected one leaves it. Its Runs are ordinary Runs of the
agent under the agent's mode.

- ``ensure_management_task`` starts the task when the agent is in Full, not paused, and
  no active signed grant's own management Task drives the account (the grant decides
  within its own terms until it is revoked, 0.4); otherwise it does nothing.
- ``end_management_task`` ends it: on the switch to Ask, a pause, a delete, or a signed
  grant's Task taking over. Ending keeps what the agent set up (``close_task``): its Runs
  go on outside the task with their Trade Approval cards still decidable, its watches
  move to its conversation, a pending timer becomes a one-shot routine there, and its
  routines are untouched; the agent keeps managing its positions in Ask.
- ``reconcile_management_tasks``, a gateway step, catches what no transition reached.

The first two are called inside the caller's transaction, under the agent's authority
lock.
"""

from typing import Any

from lonora_bus.attention import attention_text
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskCreate
from lonora_core.user_error import ToolRefusal
from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .authority_lock import authority_lock
from .client import Database
from .conversation_locale import conversation_locale
from .events import emit
from .schema import AccountAuthorityRow, AgentRow, MarketWatchRow, RunRow, TicketRow
from .tasks import create_task, save_task, task_state
from .threads import conversation_thread

MARKER = "account_management_agent"
# Set by ``close_task``, so the gateway can tell it from the owner's cancel or completion
# of the task.
CLOSED = "account_management_closed"
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


async def grant_driven(session: AsyncSession, *where: ColumnElement[bool]) -> set[str]:
    """The agents for which an active, unexpired signed grant's own management Task is
    still running: that Task drives the account until its grant is revoked or expires."""
    from lonora_session.idempotency import stable_id

    driven: set[str] = set()
    for grant in await session.scalars(
        select(AccountAuthorityRow).where(
            *where,
            AccountAuthorityRow.status == "active",
            or_(
                AccountAuthorityRow.valid_until.is_(None),
                AccountAuthorityRow.valid_until > utcnow(),
            ),
        )
    ):
        task = await session.get(TicketRow, stable_id(grant.id, "account-management-task"))
        if task is not None and task.state.get("task") and task_live(task):
            driven.add(grant.agent_id)
    return driven


async def grant_task_drives(session: AsyncSession, owner_id: str, agent_id: str) -> bool:
    """Whether a signed grant's own management Task drives this agent's account."""
    return bool(
        await grant_driven(
            session,
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == agent_id,
        )
    )


def refuse_agent_cancel(row: TicketRow) -> None:
    """The agent never cancels its own mode task: nothing would start it again while the
    agent stays in Full (4.5.2). Ask (the agent's switch or the owner's), a pause, a
    delete, a signed grant's own Task taking over, or the owner's cancel or completion
    ends it."""
    if row.agent_id and row.payload.get(MARKER) == row.agent_id:
        raise ToolRefusal(
            "management_task_cancel_forbidden",
            409,
            details={
                "class": "permission",
                "retryable": False,
                "hint": "This is your continuous Full-mode task; you cannot cancel it. It "
                "ends when you switch yourself to Ask (trading_mode_ask) or the owner "
                "switches you to Ask, when you are paused or deleted, when a signed grant's "
                "own task takes over, or when the owner cancels or completes it.",
            },
        )


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
    if await grant_task_drives(session, owner_id, agent_id):
        return None
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
            title=attention_text("full_mode_task", locale),
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


async def reconcile_management_tasks(db: Database) -> int:
    """The gateway's catch-up for what no Full tap, pause or resume reached; idempotent.

    - An agent in Full, not paused, and not driven by a signed grant's Task gets a mode
      task when it has never had one (it was in Full before this task existed), or when
      ``close_task`` ended its last one (``CLOSED``): a grant's Task took over and that
      grant has since expired, or the mode was written back to Full without a tap.
    - An open mode task of an agent in Ask, or paused, ends.

    A mode task the owner cancelled or completed, or one that failed for good, stays as
    it is; the next Full tap or resume starts a new one. Each agent runs in its own
    transaction, deciding again under its authority lock."""
    from .item_failures import ItemGuard, blocked

    mode_task = (
        TicketRow.owner_id == AgentRow.owner_id,
        TicketRow.agent_id == AgentRow.id,
        TicketRow.payload[MARKER].as_string() == AgentRow.id,
    )
    had_task = exists().where(*mode_task)
    open_task = exists().where(
        *mode_task, TicketRow.state["task"]["status"].as_string().not_in(sorted(TERMINAL))
    )
    last_closed = (
        select(TicketRow.payload[CLOSED].as_boolean())
        .where(*mode_task)
        .order_by(TicketRow.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    full = and_(AgentRow.trading_mode == "full", AgentRow.paused.is_(False))
    async with db.sessions() as session:
        # A grant-driven agent gets no task, so it would fill every batch, pass after pass.
        driven = await grant_driven(session)
        rows = list(
            await session.execute(
                select(AgentRow.id, AgentRow.owner_id)
                .where(
                    or_(
                        and_(
                            full,
                            or_(~had_task, last_closed.is_(True)),
                            AgentRow.id.not_in(driven),
                        ),
                        and_(~full, open_task),
                    ),
                    ~blocked("management_task", AgentRow.id),
                )
                .order_by(AgentRow.id)
                .limit(50)
            )
        )
    guard = ItemGuard(db, "management_task")
    await guard.prepare(agent_id for agent_id, _ in rows)
    changed = 0
    for agent_id, owner_id in rows:

        async def reconcile(agent_id: str = agent_id, owner_id: str = owner_id) -> bool:
            async with db.sessions() as session, session.begin():
                await authority_lock(session, agent_id)
                agent = await session.get(AgentRow, agent_id, populate_existing=True)
                if agent is None or agent.owner_id != owner_id:
                    return False
                if agent.trading_mode == "full" and not agent.paused:
                    last = await session.scalar(
                        select(TicketRow)
                        .where(
                            TicketRow.owner_id == owner_id,
                            TicketRow.agent_id == agent_id,
                            TicketRow.payload[MARKER].as_string() == agent_id,
                        )
                        .order_by(TicketRow.created_at.desc())
                        .limit(1)
                        .execution_options(populate_existing=True)
                    )
                    if last is not None and not last.payload.get(CLOSED):
                        return False
                    return await ensure_management_task(session, owner_id, agent_id) is not None
                if not await open_management_tasks(session, owner_id, agent_id):
                    return False
                await end_management_task(session, owner_id, agent_id)
                return True

        changed += int(bool(await guard.run(agent_id, owner_id, reconcile)))
    return changed


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
    - The task is marked ``CLOSED``: the gateway can tell it from the owner's cancel or
      completion of the task.

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
    from .cancellation import cancel_locked

    for run in runs:
        if run.model_metadata.get("task_id") != task.id:
            continue
        wait = run.execution_state.get("environment", {}).get("wait")
        if run.status == "waiting_takeover":
            # Suspended on its own wait, or held by the owner's pause of the task: only
            # the task could resume it.
            if wait and wait.get("kind") == "timer" and wait.get("due_at"):
                await keep_timer(session, task, str(wait["due_at"]))
            await cancel_locked(session, task.owner_id, run)
        elif run.status == "queued" and not started(run):
            await cancel_locked(session, task.owner_id, run)
        else:
            detach(run)
    await keep_watches(session, task)
    state = task_state(task)
    state.status, state.phase, state.control_requested = "cancelled", "cancelled", None
    state.waiting_reason = None
    if state.failure:
        state.failure.next_retry_at = None
    task.payload = {**task.payload, CLOSED: True}
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
    locale = await conversation_locale(session, task.owner_id, thread.id)
    when = datetime.fromisoformat(due_at)
    session.add(
        RoutineRow(
            owner_id=task.owner_id,
            agent_id=task.agent_id,
            thread_id=thread.id,
            # What it is, not the ended task's name (0.4).
            title=attention_text("full_mode_follow_up", locale),
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
