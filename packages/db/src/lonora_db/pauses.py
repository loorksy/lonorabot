"""Pauses of an agent's work: the agent itself, a Task, a routine or a watch.

A hold (``ln_supervision_holds``, ``SupervisionHoldRow``) records who paused a piece of
work and so who may lift it. The owner's own pause is a hold with ``source='owner'``
and no holder: the paused agent never lifts it on its own initiative, and only the
owner's resume releases it. Pausing work that already carries another agent's hold
makes that hold the owner's, never a weaker one (the holder stays named for
attribution).

Lock order: the owner's controls lock the agent, routine or watch row before its hold;
a Task's control takes the hold, then the Run, then the Task. Callers keep both
orders, so a pause or resume never deadlocks with message admission.
"""

from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, MarketWatchRow, RoutineRow, RunRow, SupervisionHoldRow, TicketRow
from .transactions import owned_agent

# A group run the owner addressed to this agent (a mention, a reply, its card), not the
# group's fallback answerer.
OWNER_ADDRESSED = "owner_addressed"


def runs_while_paused(trigger: str, metadata: dict[str, Any]) -> bool:
    """What a paused agent still runs (4.7.1): the owner's direct message, and a broker
    event on its own open positions and pending orders (an observe-only wake is activity
    on tickets it does not own). Every other run of it waits until it is resumed, so its
    routines, watches, timers, Tasks, peers and wakes are held."""
    if trigger == "broker_event":
        return metadata.get("authority") != "observe_only"
    if trigger == "group":
        return metadata.get(OWNER_ADDRESSED) is True
    return trigger == "user"


def claimable_while_paused(run: Any = RunRow) -> ColumnElement[bool]:
    """``runs_while_paused`` as a claim condition on ``run`` (``RunRow`` or an alias)."""
    authority = run.model_metadata["authority"].as_string()
    return or_(
        run.trigger == "user",
        and_(run.trigger == "group", run.model_metadata[OWNER_ADDRESSED].as_boolean()),
        and_(
            run.trigger == "broker_event",
            or_(authority.is_(None), authority != "observe_only"),
        ),
    )


async def live_hold(
    session: AsyncSession, kind: str, target_id: str, *, lock: bool = False
) -> SupervisionHoldRow | None:
    query = select(SupervisionHoldRow).where(
        SupervisionHoldRow.target_kind == kind,
        SupervisionHoldRow.target_id == target_id,
        SupervisionHoldRow.released_at.is_(None),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def work_paused(session: AsyncSession, kind: str, target_id: str) -> bool:
    """Whether the work a hold names is paused right now (a missing item is not)."""
    if kind == "agent":
        agent = await session.get(AgentRow, target_id)
        return agent is not None and agent.paused
    if kind == "routine":
        routine = await session.get(RoutineRow, target_id)
        return routine is not None and not routine.enabled
    if kind == "watch":
        watch = await session.get(MarketWatchRow, target_id)
        return watch is not None and not watch.payload.get("enabled", True)
    from .tasks import task_state

    task = await session.get(TicketRow, target_id)
    if task is None or not task.state.get("task"):
        return False
    state = task_state(task)
    # A pause asked of a working Task takes effect at its next safe boundary.
    return state.status == "paused" or state.control_requested == "pause"


async def release_hold(session: AsyncSession, hold: SupervisionHoldRow, by: str) -> None:
    """The hold ends; its card reads the hold, so it stops offering Resume by itself."""
    hold.released_at, hold.released_by = utcnow(), by
    await session.flush()


async def owner_takes_over(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    target_id: str,
    *,
    paused: bool,
    agent_id: str | None,
) -> None:
    """The owner itself paused or cancelled (``paused``), or resumed, this work of
    ``agent_id``. The owner's pause is a hold of its own (``source='owner'``, no holder),
    so the paused agent never lifts it on its own initiative, and a supervisor's hold on
    it becomes the owner's, never a weaker one: the supervisor stays named, but only the
    owner lifts it. The owner's resume releases it."""
    hold = await live_hold(session, kind, target_id, lock=True)
    if hold is not None and hold.owner_id != owner_id:
        return
    if not paused:
        if hold is not None:
            await release_hold(session, hold, "owner")
        return
    if hold is None:
        if agent_id is None:
            return  # Work of no agent: there is nobody who could lift it.
        session.add(
            SupervisionHoldRow(
                owner_id=owner_id,
                holder_agent_id=None,
                agent_id=agent_id,
                target_kind=kind,
                target_id=target_id,
                source="owner",
                created_at=utcnow(),
            )
        )
        await session.flush()
    elif hold.source != "owner":
        hold.source = "owner"
        await session.flush()


async def owner_holds_for(session: AsyncSession, owner_id: str, holder_id: str) -> None:
    """A supervisor is being deleted: every pause it holds stays in force as the
    owner's (its card keeps offering Resume), so nothing it paused is resumed, and no
    pause becomes one the paused agent could lift. The row loses its holder when the
    agent row goes (``ON DELETE SET NULL``)."""
    holds = await session.scalars(
        select(SupervisionHoldRow)
        .where(
            SupervisionHoldRow.owner_id == owner_id,
            SupervisionHoldRow.holder_agent_id == holder_id,
            SupervisionHoldRow.released_at.is_(None),
        )
        .with_for_update()
    )
    for hold in holds:
        hold.source = "owner"
    await session.flush()


async def refuse_held(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    target_id: str,
    agent_id: str,
    *,
    owner_message: bool = False,
) -> None:
    """The paused agent never resumes held work on its own initiative: it asks the
    supervisor or the owner. In a run that answers the owner's untainted message a team
    agent resumes a supervisor's hold (released as the owner's); Lonora lifts only pauses
    it made. A pause the owner holds is lifted only by the owner: one the owner asked for
    in chat also from the owner's message, the owner's own pause from a control only from
    a control. A hold on work that is no longer paused is stale and released."""
    hold = await live_hold(session, kind, target_id, lock=True)
    if hold is None or hold.owner_id != owner_id:
        return
    if not await work_paused(session, kind, target_id):
        await release_hold(session, hold, "stale")
        return
    if hold.source == "owner":
        if owner_message and hold.source_message_id is not None:
            # A pause the owner asked for in chat, lifted when the owner asks in chat.
            await release_hold(session, hold, "owner")
            return
        raise LonoraError("work_paused_by_owner", 409)
    if hold.holder_agent_id == agent_id:
        return
    agent = await session.get(AgentRow, agent_id)
    if not owner_message or (agent is not None and agent.role == "personal"):
        # Lonora lifts only the pauses Lonora made (4.7.2), even from the owner's words.
        raise LonoraError("work_paused_by_supervisor", 409)
    await release_hold(session, hold, "owner")


async def owner_resumes(session: AsyncSession, owner_id: str, hold_id: str) -> str:
    """The owner's Resume on a pause card: the owner's own resume of that work, which
    releases the hold whoever holds it. Returns what was resumed."""
    hold = await session.get(SupervisionHoldRow, hold_id)
    if hold is None or hold.owner_id != owner_id:
        raise LonoraError("supervision_hold_not_found", 404)
    kind, target_id = hold.target_kind, hold.target_id
    if kind == "agent":
        from .agents import agent_data
        from .authority_lock import authority_lock
        from .management_task import ensure_management_task

        await authority_lock(session, target_id)
        agent = await owned_agent(session, owner_id, target_id, lock=True)
        await owner_takes_over(
            session, owner_id, kind, target_id, paused=False, agent_id=hold.agent_id
        )
        if agent.paused:
            agent.paused = False
            emit(session, owner_id, "agent.updated", agent_id=agent.id, payload=agent_data(agent))
            await session.flush()
            # Resuming a Full agent starts its continuous task again (4.5.1).
            await ensure_management_task(session, owner_id, agent.id)
    elif kind == "routine":
        from .routines import owned_routine

        routine = await owned_routine(session, owner_id, target_id)
        await owner_takes_over(
            session, owner_id, kind, target_id, paused=False, agent_id=hold.agent_id
        )
        routine.enabled = True
    elif kind == "watch":
        from .market_watches import control_watch

        await control_watch(session, owner_id, target_id, "resume")
    else:
        from lonora_contracts.tasks import TaskControl

        from .tasks import control_task, get_task

        task = await get_task(session, owner_id, target_id)
        await control_task(
            session,
            owner_id,
            TaskControl(task_id=target_id, action="resume", expected_version=task.version),
        )
    return kind
