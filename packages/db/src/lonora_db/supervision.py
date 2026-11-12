"""Supervision: one agent reads and steers another agent's work, visibly and revocably.

A grant (``ln_supervision_grants``) lets the supervisor read the supervised agent's
threads, runs, decisions, memory and records (``session_search``, ``search_internal``,
``subagent_inspect``, ``agent_inspect``), message it, pause or resume its work
(``agent_control``, ``routine_toggle``) and add narrowing pauses on its trading
(``trade_restriction_create``). It never trades for it, never uses its grant, never
lifts a brake and never edits its memory or instructions. Agents without a grant stay
private from each other.

The Personal Agent holds a ``default`` grant over every agent from the agent's creation
(migration ``0041_supervision_grants`` seeds existing agents). Another agent becomes a
supervisor only from the owner's message, recorded as the grant's source, or from the
owner's tap on a card. The owner sees every grant on the agents' profiles and in chat
and revokes one with one tap; a revoked grant ends every read and control at once.

Holds (``ln_supervision_holds``) record the pauses a supervisor put on another agent's
work: the agent itself, a Task, a routine or a watch. On its own initiative only the
supervisor that set a hold lifts it, while it still supervises; a run that answers the
owner's message lifts any supervisor's hold (the owner's command wins). The owner
pausing the same work makes the hold the owner's (``source='owner'``, the supervisor
kept for attribution): then only the owner lifts it, from the work itself or the card.
The owner resuming the work releases it. The paused agent never resumes held work on
its own initiative. Each pause raises a card in the paused agent's conversation that
names the supervisor, with one-tap Resume.

Pausing a whole agent stops its runs, so it could no longer close a position, cancel an
order or run an exit the owner approves. On its own initiative a supervisor therefore
never pauses an agent with money standing (bound to an account, trading with the
owner's approval or under a grant, or with operations the executor recorded for it); it
narrows that agent with ``trade_restriction_create`` and pauses its routines, watches or
Tasks instead. Only the owner pauses the Personal Agent, the owner's entry point.

The cycle rule: an agent cannot pause or narrow an agent that holds an active pause over
it, unless the owner's message asks for it. Every intervention is an event recorded for
both agents.
"""

from collections.abc import Iterable
from typing import Any, Literal

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .pauses import live_hold, release_hold, work_paused
from .schema import (
    AgentRow,
    MarketWatchRow,
    RoutineRow,
    SupervisionGrantRow,
    SupervisionHoldRow,
    TicketRow,
    TradingJournalRow,
    TradingRestrictionRow,
)
from .transactions import owned_agent

GrantVia = Literal["default", "owner_ui", "owner_message", "owner_card"]
RevokeVia = Literal["owner_ui", "owner_card", "owner_message"]
HoldKind = Literal["agent", "task", "routine", "watch"]
# agent: the supervisor on its own; owner_message: the supervisor from the owner's
# message; owner: the owner paused the same work, so the pause is the owner's now.
HoldSource = Literal["agent", "owner_message", "owner"]
# Agents one call or card may put under one supervisor.
MAXIMUM_SUPERVISED_PER_CHANGE = 10


async def lock_supervision(session: AsyncSession, owner_id: str) -> None:
    """Serialize grant changes per owner, so a pair has at most one active grant."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "supervision:" + owner_id},
        )


def _active(owner_id: str) -> Any:
    return (SupervisionGrantRow.owner_id == owner_id) & SupervisionGrantRow.revoked_at.is_(None)


async def supervised_ids(session: AsyncSession, owner_id: str, supervisor_id: str) -> list[str]:
    """The agents this one supervises now, in a stable order."""
    rows = await session.scalars(
        select(SupervisionGrantRow.supervised_agent_id)
        .where(_active(owner_id), SupervisionGrantRow.supervisor_agent_id == supervisor_id)
        .order_by(SupervisionGrantRow.created_at, SupervisionGrantRow.supervised_agent_id)
    )
    return list(rows)


async def supervisor_ids(session: AsyncSession, owner_id: str, agent_id: str) -> list[str]:
    rows = await session.scalars(
        select(SupervisionGrantRow.supervisor_agent_id)
        .where(_active(owner_id), SupervisionGrantRow.supervised_agent_id == agent_id)
        .order_by(SupervisionGrantRow.created_at, SupervisionGrantRow.supervisor_agent_id)
    )
    return list(rows)


async def supervises(
    session: AsyncSession, owner_id: str, supervisor_id: str, agent_id: str
) -> bool:
    found = await session.scalar(
        select(SupervisionGrantRow.id)
        .where(
            _active(owner_id),
            SupervisionGrantRow.supervisor_agent_id == supervisor_id,
            SupervisionGrantRow.supervised_agent_id == agent_id,
        )
        .limit(1)
    )
    return found is not None


async def supervises_all(session: AsyncSession, owner_id: str, supervisor_id: str) -> bool:
    """Whether this agent supervises every other agent of the owner right now."""
    others = set(
        await session.scalars(
            select(AgentRow.id).where(AgentRow.owner_id == owner_id, AgentRow.id != supervisor_id)
        )
    )
    return others <= set(await supervised_ids(session, owner_id, supervisor_id))


async def require_supervision(
    session: AsyncSession, owner_id: str, supervisor_id: str, agent_id: str
) -> AgentRow:
    """The supervised agent, or 403 when this agent does not supervise it now."""
    agent = await owned_agent(session, owner_id, agent_id)
    if agent.id == supervisor_id:
        raise LonoraError("supervision_self_target", 409)
    if not await supervises(session, owner_id, supervisor_id, agent.id):
        raise LonoraError("supervision_required", 403)
    return agent


def _grant_payload(row: SupervisionGrantRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "supervisor_agent_id": row.supervisor_agent_id,
        "supervised_agent_id": row.supervised_agent_id,
        "created_via": row.created_via,
        "revoked_via": row.revoked_via,
    }


def _grant_events(session: AsyncSession, row: SupervisionGrantRow, kind: str) -> None:
    """Recorded for both agents: each sees who supervises it and whom it supervises."""
    for agent_id in (row.supervisor_agent_id, row.supervised_agent_id):
        emit(session, row.owner_id, kind, agent_id=agent_id, payload=_grant_payload(row))


async def grant_supervision(
    session: AsyncSession,
    owner_id: str,
    supervisor_id: str,
    supervised_id: str,
    *,
    via: GrantVia,
    created_by_agent_id: str | None = None,
    source_message_id: str | None = None,
) -> tuple[SupervisionGrantRow, bool]:
    """The active grant for the pair and whether it is new; a repeat changes nothing."""
    await lock_supervision(session, owner_id)
    if supervisor_id == supervised_id:
        raise LonoraError("supervision_self_target", 409)
    supervisor = await owned_agent(session, owner_id, supervisor_id)
    await owned_agent(session, owner_id, supervised_id)
    if supervisor.role == "delegated":
        # A temporary helper holds no standing responsibility over other agents.
        raise LonoraError("supervision_supervisor_invalid", 422)
    existing = await session.scalar(
        select(SupervisionGrantRow).where(
            _active(owner_id),
            SupervisionGrantRow.supervisor_agent_id == supervisor_id,
            SupervisionGrantRow.supervised_agent_id == supervised_id,
        )
    )
    if existing is not None:
        return existing, False
    row = SupervisionGrantRow(
        owner_id=owner_id,
        supervisor_agent_id=supervisor_id,
        supervised_agent_id=supervised_id,
        created_via=via,
        created_by_agent_id=created_by_agent_id,
        source_message_id=source_message_id,
        created_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    _grant_events(session, row, "supervision.granted")
    return row, True


async def owned_grant(
    session: AsyncSession, owner_id: str, grant_id: str, *, lock: bool = False
) -> SupervisionGrantRow:
    row = await session.get(
        SupervisionGrantRow, grant_id, with_for_update=lock, populate_existing=lock
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("supervision_grant_not_found", 404)
    return row


async def revoke_supervision(
    session: AsyncSession, owner_id: str, grant_id: str, *, via: RevokeVia
) -> SupervisionGrantRow:
    """End a grant now; revoking an ended grant changes nothing. Holds the supervisor
    set stay in force (they only narrow); the owner lifts them on the work itself."""
    await lock_supervision(session, owner_id)
    row = await owned_grant(session, owner_id, grant_id, lock=True)
    if row.revoked_at is None:
        row.revoked_at, row.revoked_via = utcnow(), via
        await session.flush()
        _grant_events(session, row, "supervision.revoked")
    return row


async def personal_agent_id(session: AsyncSession, owner_id: str) -> str | None:
    return await session.scalar(
        select(AgentRow.id).where(AgentRow.owner_id == owner_id, AgentRow.role == "personal")
    )


async def grant_default(session: AsyncSession, owner_id: str, agent: AgentRow) -> None:
    """A new agent is supervised by the Personal Agent from its creation."""
    personal = await personal_agent_id(session, owner_id)
    if personal is None or personal == agent.id or agent.role == "personal":
        return
    await grant_supervision(session, owner_id, personal, agent.id, via="default")


async def seed_personal_grants(session: AsyncSession, owner_id: str, personal_id: str) -> int:
    """A Personal Agent created after other agents supervises each of them by default."""
    others = list(
        await session.scalars(
            select(AgentRow.id)
            .where(AgentRow.owner_id == owner_id, AgentRow.id != personal_id)
            .order_by(AgentRow.created_at, AgentRow.id)
        )
    )
    created = 0
    for agent_id in others:
        _, new = await grant_supervision(session, owner_id, personal_id, agent_id, via="default")
        created += new
    return created


async def agent_names(
    session: AsyncSession, owner_id: str, ids: Iterable[str | None]
) -> dict[str, str]:
    wanted = sorted({identifier for identifier in ids if identifier})
    if not wanted:
        return {}
    rows = await session.execute(
        select(AgentRow.id, AgentRow.name).where(
            AgentRow.owner_id == owner_id, AgentRow.id.in_(wanted)
        )
    )
    return {str(identity): str(name) for identity, name in rows}


def grant_data(row: SupervisionGrantRow, names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "supervisor": {
            "id": row.supervisor_agent_id,
            "name": names.get(row.supervisor_agent_id),
        },
        "supervised": {
            "id": row.supervised_agent_id,
            "name": names.get(row.supervised_agent_id),
        },
        "created_via": row.created_via,
        "created_at": row.created_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoked_via": row.revoked_via,
    }


async def supervision_view(session: AsyncSession, owner_id: str, agent_id: str) -> dict[str, Any]:
    """The active grants around one agent: whom it supervises and who supervises it."""
    await owned_agent(session, owner_id, agent_id)
    rows = list(
        await session.scalars(
            select(SupervisionGrantRow)
            .where(
                _active(owner_id),
                or_(
                    SupervisionGrantRow.supervisor_agent_id == agent_id,
                    SupervisionGrantRow.supervised_agent_id == agent_id,
                ),
            )
            .order_by(SupervisionGrantRow.created_at, SupervisionGrantRow.id)
        )
    )
    names = await agent_names(
        session,
        owner_id,
        {row.supervisor_agent_id for row in rows} | {row.supervised_agent_id for row in rows},
    )
    return {
        "agent_id": agent_id,
        "supervises": [
            grant_data(row, names) for row in rows if row.supervisor_agent_id == agent_id
        ],
        "supervised_by": [
            grant_data(row, names) for row in rows if row.supervised_agent_id == agent_id
        ],
    }


# Holds: pauses a supervisor put on another agent's work (the hold primitives are in
# ``pauses.py``).


async def holds_over(session: AsyncSession, owner_id: str, holder_id: str, agent_id: str) -> bool:
    """Whether ``holder_id`` holds an active pause over ``agent_id``: a live hold on that
    agent or its work, or a pause the holder recorded on its own initiative that still
    binds that agent (an owner-message pause is the owner's)."""
    holds = list(
        await session.scalars(
            select(SupervisionHoldRow).where(
                SupervisionHoldRow.owner_id == owner_id,
                SupervisionHoldRow.holder_agent_id == holder_id,
                SupervisionHoldRow.agent_id == agent_id,
                # A pause the owner took over is the owner's, not the holder's.
                SupervisionHoldRow.source != "owner",
                SupervisionHoldRow.released_at.is_(None),
            )
        )
    )
    for hold in holds:
        if await work_paused(session, hold.target_kind, hold.target_id):
            return True
    now = utcnow()
    restriction = await session.scalar(
        select(TradingRestrictionRow.id)
        .where(
            TradingRestrictionRow.owner_id == owner_id,
            TradingRestrictionRow.created_by_agent_id == holder_id,
            TradingRestrictionRow.source == "agent",
            TradingRestrictionRow.revoked_at.is_(None),
            or_(
                TradingRestrictionRow.agent_id == agent_id, TradingRestrictionRow.agent_id.is_(None)
            ),
            or_(
                TradingRestrictionRow.valid_until.is_(None),
                TradingRestrictionRow.valid_until > now,
            ),
        )
        .limit(1)
    )
    return restriction is not None


async def check_cycle(
    session: AsyncSession,
    owner_id: str,
    actor_id: str,
    targets: list[str],
    *,
    owner_message: bool,
) -> None:
    """Refuse a pause or a narrowing on an agent that holds an active pause over the
    actor; the owner's message in the actor's run wins over the rule."""
    if owner_message:
        return
    for target_id in targets:
        if target_id != actor_id and await holds_over(session, owner_id, target_id, actor_id):
            raise LonoraError("supervision_cycle", 409)


def record_intervention(
    session: AsyncSession,
    owner_id: str,
    *,
    actor_id: str,
    agent_id: str,
    payload: dict[str, Any],
    run_id: str | None = None,
) -> None:
    """One event for the agent that acted and one for the agent it acted on."""
    body = {"actor_agent_id": actor_id, "agent_id": agent_id, **payload}
    for subject in (actor_id, agent_id):
        emit(
            session,
            owner_id,
            "supervision.intervention",
            agent_id=subject,
            run_id=run_id if subject == actor_id else None,
            payload=body,
        )


WorkAction = Literal["pause", "resume"]


async def money_standing(session: AsyncSession, owner_id: str, agent: AgentRow) -> bool:
    """Whether a paused agent could leave money unattended: it is bound to an account,
    trades with the owner's approval or under a signed grant, or the executor recorded
    live operations for it (positions it opened may still be open). Pausing it would
    stop the runs that close, cancel, tighten a stop or run an approved exit."""
    if agent.trading_account_id:
        return True
    from .agent_permissions import effective_permission

    if await effective_permission(session, owner_id, agent.id) != "analysis":
        return True
    producer = TradingJournalRow.result["details"]["execution"]["agent_id"].as_string()
    operation = await session.scalar(
        select(TradingJournalRow.operation_id)
        .where(
            TradingJournalRow.owner_id == owner_id,
            producer == agent.id,
        )
        .limit(1)
    )
    return operation is not None


async def _owned_work(
    session: AsyncSession, owner_id: str, agent_id: str, kind: str, target_id: str
) -> None:
    """The item exists and is this agent's own; anything else reads as not found.

    Lock order: the owner's own controls lock the agent, routine or watch row before its
    hold, so this does the same. A Task is not locked here: its control takes the hold,
    then the Run, then the Task, on the owner's path and on this one alike.
    """
    if kind == "agent":
        await owned_agent(session, owner_id, agent_id, lock=True)
        return
    row: RoutineRow | MarketWatchRow | TicketRow | None
    if kind == "routine":
        row = await session.get(RoutineRow, target_id, with_for_update=True, populate_existing=True)
        missing = "routine_not_found"
    elif kind == "watch":
        row = await session.get(
            MarketWatchRow, target_id, with_for_update=True, populate_existing=True
        )
        missing = "market_watches_not_found"
    else:
        row, missing = await session.get(TicketRow, target_id), "task_not_found"
        if row is not None and not row.state.get("task"):
            row = None
    if row is None or row.owner_id != owner_id or row.agent_id != agent_id:
        raise LonoraError(missing, 404)


async def _cancelled_by_agent(session: AsyncSession, watch_id: str) -> bool:
    from .market_watches import STOP_CODES

    watch = await session.get(MarketWatchRow, watch_id)
    return watch is not None and watch.state.get("code") == STOP_CODES["cancel"]


async def _apply(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    kind: str,
    target_id: str,
    action: WorkAction,
) -> None:
    """Pause or resume through each item's own control, as the agent's own steering
    (holds are settled by the caller, so the item's own hold checks pass)."""
    if kind == "agent":
        from .agents import agent_data

        agent = await owned_agent(session, owner_id, agent_id, lock=True)
        agent.paused = action == "pause"
        emit(session, owner_id, "agent.updated", agent_id=agent_id, payload=agent_data(agent))
    elif kind == "routine":
        from .routines import owned_routine

        routine = await owned_routine(session, owner_id, target_id)
        routine.enabled = action == "resume"
    elif kind == "watch":
        from .market_watches import control_watch

        await control_watch(session, owner_id, target_id, action, agent_id=agent_id)
    else:
        from lonora_contracts.tasks import TaskControl

        from .tasks import control_task, get_task

        task = await get_task(session, owner_id, target_id)
        await control_task(
            session,
            owner_id,
            TaskControl(task_id=target_id, action=action, expected_version=task.version),
            agent_id=agent_id,
        )


async def control_work(
    session: AsyncSession,
    owner_id: str,
    *,
    actor_id: str,
    agent_id: str,
    kind: HoldKind,
    target_id: str | None,
    action: WorkAction,
    owner_message_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    """A supervisor pauses or resumes another agent's work (the agent itself, a Task, a
    routine or a watch). Repeating either changes nothing.

    Pausing and resuming need the grant (Lonora also acts on the owner's message without
    one), and pausing passes the cycle rule. Without the owner's message it never pauses a whole agent with money
    standing, and no agent ever pauses the Personal Agent itself. Each pause raises a
    card in the paused agent's conversation naming the supervisor, with Resume.

    Resuming on its own initiative lifts only a hold this agent set on its own. With the
    owner's message it lifts any supervisor's hold. A pause the owner holds, the owner's
    pause without a hold and the agent's own stay until they lift them. A watch the
    agent cancelled itself while held stays cancelled; the resume only ends the hold.
    """
    owner_message = owner_message_id is not None
    agent = await owned_agent(session, owner_id, agent_id)
    if agent.id == actor_id:
        raise LonoraError("supervision_self_target", 409)
    if not await supervises(session, owner_id, actor_id, agent.id) and not (
        # The owner's message routes through Lonora, the owner's entry point; any other
        # agent steers another only under a visible grant, whatever a message said.
        owner_message and actor_id == await personal_agent_id(session, owner_id)
    ):
        raise LonoraError("supervision_required", 403)
    item = agent.id if kind == "agent" else target_id
    if not item:
        raise LonoraError("supervision_target_required", 422)
    await _owned_work(session, owner_id, agent.id, kind, item)
    hold = await live_hold(session, kind, item, lock=True)
    paused = await work_paused(session, kind, item)
    if hold is not None and not paused:
        await release_hold(session, hold, "stale")
        hold = None
    result: dict[str, Any] = {"agent_id": agent.id, "target": kind, "target_id": item}
    if action == "pause":
        if paused:
            held_by = (
                "owner_or_the_agent"
                if hold is None
                else "owner"
                if hold.source == "owner"
                else "you"
                if hold.holder_agent_id == actor_id
                else "another_agent"
            )
            return {**result, "changed": False, "paused": True, "paused_by": held_by}
        if kind == "agent" and agent.role == "personal":
            # The owner's entry point: only the owner pauses it, from its profile.
            raise LonoraError("supervision_personal_agent", 403)
        if kind == "agent" and not owner_message and await money_standing(session, owner_id, agent):
            # Its exits would stop too: narrow it with trade_restriction_create and pause
            # its routines, watches or Tasks; the whole agent only when the owner asks.
            raise LonoraError("supervision_pause_trading_agent", 403)
        await check_cycle(session, owner_id, actor_id, [agent.id], owner_message=owner_message)
        await _apply(session, owner_id, agent.id, kind, item, "pause")
        hold = SupervisionHoldRow(
            owner_id=owner_id,
            holder_agent_id=actor_id,
            agent_id=agent.id,
            target_kind=kind,
            target_id=item,
            source="owner_message" if owner_message else "agent",
            source_message_id=owner_message_id,
            source_run_id=run_id,
            created_at=utcnow(),
        )
        session.add(hold)
        await session.flush()
        from .owner_actions import raise_supervision_pause_card

        await raise_supervision_pause_card(session, hold, run_id=run_id)
    else:
        if not paused:
            return {**result, "changed": False, "paused": False}
        if hold is None or hold.source == "owner":
            # The owner's pause or the agent's own: only they lift it.
            raise LonoraError("supervision_resume_not_yours", 403)
        if not owner_message:
            if hold.holder_agent_id != actor_id:
                raise LonoraError("supervision_resume_not_yours", 403)
            if hold.source == "owner_message":
                raise LonoraError("supervision_resume_needs_owner_message", 403)
        await release_hold(session, hold, "holder" if hold.holder_agent_id == actor_id else "owner")
        if kind == "watch" and await _cancelled_by_agent(session, item):
            # The agent cancelled the held watch itself: its own choice stays.
            result["stays_cancelled_by_the_agent"] = True
        else:
            await _apply(session, owner_id, agent.id, kind, item, "resume")
    record_intervention(
        session,
        owner_id,
        actor_id=actor_id,
        agent_id=agent.id,
        payload={
            "action": action,
            "target": kind,
            "target_id": item,
            "source": "owner_message" if owner_message else "agent",
        },
        run_id=run_id,
    )
    return {**result, "changed": True, "paused": action == "pause"}
