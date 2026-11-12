"""The continuous account-management task of Full mode (mandate 4.5, 14.3.3).

An agent in Full that is not paused has exactly one continuous Task, keyed by the agent
(its kickoff Run carries ``account_management_id`` = the agent's id, the recovery path
of ``is_continuous_task``). It is bound to no account: every wake reads the accounts
connected at that moment, so a newly connected account joins it and a disconnected one
leaves it. Its Runs are ordinary Runs of the agent under the agent's mode.

- ``ensure_management_task`` starts the task when the agent is in Full, not paused, and
  no active signed grant's own management Task drives the account (the grant decides
  within its own terms until it is revoked, 0.4); otherwise it does nothing.
- ``end_management_task`` ends it: on the switch to Ask, a pause, a delete, or a signed
  grant's Task taking over. Ending keeps the agent's watches (they move to the agent's
  conversation), routines and approvals; the agent keeps managing its positions in Ask.

Both are called inside the caller's transaction, under the agent's authority lock.
"""

from typing import Any

from lonora_bus.attention import attention_text
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskCreate
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .authority_lock import authority_lock
from .conversation_locale import conversation_locale
from .events import emit
from .schema import AccountAuthorityRow, AgentRow, MarketWatchRow, RunRow, TicketRow
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


async def live_management_task(
    session: AsyncSession, owner_id: str, agent_id: str
) -> TicketRow | None:
    """The agent's mode task that has not ended (it may be paused by the owner)."""
    for row in await session.scalars(
        select(TicketRow)
        .where(
            TicketRow.owner_id == owner_id,
            TicketRow.agent_id == agent_id,
            TicketRow.payload[MARKER].as_string() == agent_id,
        )
        .order_by(TicketRow.created_at.desc())
        .execution_options(populate_existing=True)
    ):
        if task_live(row):
            return row
    return None


def task_live(row: TicketRow) -> bool:
    """Not ended and not asked to end; a failed Task counts only while a retry is due."""
    state = task_state(row)
    if state.status in TERMINAL or state.control_requested in {"cancel", "complete"}:
        return False
    return state.status != "failed" or bool(state.failure and state.failure.next_retry_at)


async def grant_task_drives(session: AsyncSession, owner_id: str, agent_id: str) -> bool:
    """Whether an active, unexpired signed grant's own management Task is still running
    for this agent: that Task drives the account until its grant is revoked."""
    from lonora_session.idempotency import stable_id

    for grant in await session.scalars(
        select(AccountAuthorityRow).where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == agent_id,
            AccountAuthorityRow.status == "active",
            or_(
                AccountAuthorityRow.valid_until.is_(None),
                AccountAuthorityRow.valid_until > utcnow(),
            ),
        )
    ):
        task = await session.get(TicketRow, stable_id(grant.id, "account-management-task"))
        if task is not None and task.state.get("task") and task_live(task):
            return True
    return False


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
    """End the agent's mode task, if one is live, as the owner's cancel of a Task does: a
    queued or waiting Run stops now and the Trade Approval cards it waits on end with it
    (the switch to Ask is a mode change, a delete withdraws them, a paused agent may not
    add risk); a working Run stops at its next checkpoint. Its watches move to the
    agent's own conversation and keep watching; routines and the journal are untouched.
    Locks follow the Task order elsewhere: the Run, then the Task."""
    from .tasks import cancel_task_approvals

    await authority_lock(session, agent_id)
    found = await live_management_task(session, owner_id, agent_id)
    if found is None:
        return
    current = await active_run(session, found)
    task = await session.get(TicketRow, found.id, with_for_update=True, populate_existing=True)
    if task is None or not task_live(task):
        return
    await keep_watches(session, task)
    state = task_state(task)
    if current is not None and current.status in {"queued", "waiting_input", "waiting_takeover"}:
        current.status = "cancelled"
        current.updated_at = utcnow()
        await cancel_task_approvals(session, current.id)
    if current is not None and current.status in {"leased", "running"}:
        state.control_requested = "cancel"
    else:
        state.status, state.phase, state.control_requested = "cancelled", "cancelled", None
        state.waiting_reason = None
    save_task(session, task, state)


async def active_run(session: AsyncSession, task: TicketRow) -> RunRow | None:
    return await session.scalar(
        select(RunRow)
        .where(
            RunRow.thread_id == task.thread_id,
            RunRow.agent_id == task.agent_id,
            RunRow.status.in_(["queued", "leased", "running", "waiting_input", "waiting_takeover"]),
        )
        .order_by(RunRow.created_at.desc())
        .limit(1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


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
