"""Lonora steers a team agent's work: pauses, holds and the record of each intervention.

Only Lonora, by its built-in lead role (``lead.py``), reads and steers another agent
(3.3.1: two levels, no supervision grants). It pauses or resumes a team agent's work
(``agent_control``, ``routine_toggle``): the agent itself, a Task, a routine or a watch.
It never trades for it, lifts a brake or edits its memory or instructions.

Holds (``ln_supervision_holds``) record those pauses. On its own initiative Lonora lifts
only the pauses it made (4.7.2). A pause made from the owner's message, and the owner
pausing the same work, make the hold the owner's (``source='owner'``, the agent kept
for attribution): then only the owner lifts it, from the work itself or the card. The
owner resuming the work releases it. The paused agent never resumes held work on its own
initiative. Holds and pause cards an earlier team supervisor left stay readable; the
owner's Resume lifts them.

Pausing a whole agent never stops its exits: a paused agent still wakes for its own
positions and pending orders and sends risk-reducing requests (4.7.1). Only the owner
pauses the Personal Agent, the owner's entry point. Every intervention is an event
recorded for both agents.
"""

from collections.abc import Iterable
from typing import Any, Literal

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .lead import is_lead, personal_agent_id, reaches
from .pauses import live_hold, release_hold, work_paused
from .schema import (
    AgentRow,
    MarketWatchRow,
    RoutineRow,
    SupervisionHoldRow,
    TicketRow,
    TradingJournalRow,
)
from .transactions import owned_agent

HoldKind = Literal["agent", "task", "routine", "watch"]
# agent: the supervisor (or Lonora) on its own; owner: the owner's pause, made by the
# owner or by an agent from the owner's message (the holder kept for attribution, 4.7.2).
HoldSource = Literal["agent", "owner"]


async def require_supervision(
    session: AsyncSession, owner_id: str, supervisor_id: str, agent_id: str
) -> AgentRow:
    """The supervised agent, or 403 when this agent neither leads (Lonora) nor
    supervises it now."""
    agent = await owned_agent(session, owner_id, agent_id)
    if agent.id == supervisor_id:
        raise LonoraError("supervision_self_target", 409)
    if not await reaches(session, owner_id, supervisor_id, agent.id):
        raise LonoraError("supervision_required", 403)
    return agent


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


# Holds: pauses a supervisor put on another agent's work (the hold primitives are in
# ``pauses.py``).


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
    """Whether an agent may have money standing: it is bound to an account, or the
    executor recorded operations for it (positions and orders it opened may still be
    open). Paused, it still wakes for them and reduces their risk (4.7.1)."""
    if agent.trading_account_id:
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
        from .management_task import ensure_management_task

        agent = await owned_agent(session, owner_id, agent_id, lock=True)
        agent.paused = action == "pause"
        emit(session, owner_id, "agent.updated", agent_id=agent_id, payload=agent_data(agent))
        # Pausing ended the Full-mode task in control_work; resuming starts it again.
        if action == "resume":
            await session.flush()
            await ensure_management_task(session, owner_id, agent_id)
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
    """Lonora pauses or resumes a team agent's work (the agent itself, a Task, a routine
    or a watch). Repeating either changes nothing.

    Only the lead reaches another agent (``lead.reaches``); a team agent is refused
    (``supervision_required``). No agent ever pauses the Personal Agent itself. Lonora
    may pause a trading agent, since a paused agent still reduces its risk (4.7.1), and
    its pause raises no card (it reports in one line). The branches below for a non-lead
    supervisor (the money-standing refusal, lifting another supervisor's hold, the
    supervisor's pause card) are no longer reached; they go with W-PAUSE's rewrite of
    ``money_standing`` (14.3.7).

    Resuming on its own initiative lifts only a hold Lonora set on its own (4.7.2). A
    pause made from the owner's message is the owner's (``source='owner'``, the actor kept
    as holder). A pause the owner holds, the owner's pause without a hold and the agent's
    own stay until they lift them. A watch the agent cancelled itself while held stays
    cancelled; the resume only ends the hold.
    """
    owner_message = owner_message_id is not None
    if kind == "agent":
        from .authority_lock import authority_lock

        # Taken before the agent's row lock, in the order a mode change takes them.
        await authority_lock(session, agent_id)
        if action == "pause":
            from .management_task import end_management_task

            # Pausing ends the Full-mode task (4.5.2), before the agent's row lock: the
            # task's Runs are locked first, as their own work does. A refusal below rolls
            # the whole transaction back.
            await end_management_task(session, owner_id, agent_id)
    # A pause asked for in the owner's words is the owner's (4.7.2). Only an untainted
    # owner message stands for them (6.10): injected text never speaks as the owner.
    asked_by_owner = owner_message_id
    agent = await owned_agent(session, owner_id, agent_id)
    if agent.id == actor_id:
        raise LonoraError("supervision_self_target", 409)
    # Lonora steers every team agent by its built-in lead role; no other agent steers
    # another (3.3.1), whatever a message said.
    if not await reaches(session, owner_id, actor_id, agent.id):
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
        if paused and asked_by_owner and (hold is None or hold.source != "owner"):
            # The owner asks to pause work that is already paused: the pause becomes the
            # owner's, so neither the agent nor the one that paused it lifts it alone.
            if hold is None:
                session.add(
                    SupervisionHoldRow(
                        owner_id=owner_id,
                        holder_agent_id=actor_id,
                        agent_id=agent.id,
                        target_kind=kind,
                        target_id=item,
                        source="owner",
                        source_message_id=asked_by_owner,
                        source_run_id=run_id,
                        created_at=utcnow(),
                    )
                )
            else:
                hold.source = "owner"
            await session.flush()
            return {**result, "changed": False, "paused": True, "paused_by": "owner"}
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
        if (
            kind == "agent"
            and not owner_message
            and actor_id != await personal_agent_id(session, owner_id)
            and await money_standing(session, owner_id, agent)
        ):
            # Supervision is removed in phase 6 and is not extended (0.4): a team
            # supervisor still pauses only an agent's routines, watches or Tasks on its own.
            # Lonora's pause of a trading agent stands (its exits continue, 4.7.1).
            raise LonoraError("supervision_pause_trading_agent", 403)
        # No cycle rule: only the lead pauses another agent, and only the owner pauses the
        # lead (3.1.2, 3.3.1). A pause an earlier team supervisor left never blocks it.
        await _apply(session, owner_id, agent.id, kind, item, "pause")
        hold = SupervisionHoldRow(
            owner_id=owner_id,
            holder_agent_id=actor_id,
            agent_id=agent.id,
            target_kind=kind,
            target_id=item,
            # A pause the owner asked for in chat is the owner's: only the owner lifts it.
            source="owner" if asked_by_owner else "agent",
            source_message_id=asked_by_owner,
            source_run_id=run_id,
            created_at=utcnow(),
        )
        session.add(hold)
        await session.flush()
        if not await is_lead(session, owner_id, actor_id):
            from .owner_actions import raise_supervision_pause_card

            # Lonora's pause raises no card (only the five fixed cards, 10.3): Lonora tells
            # the owner in one line. Other supervisors keep theirs until supervision goes.
            await raise_supervision_pause_card(session, hold, run_id=run_id)
    else:
        if not paused:
            return {**result, "changed": False, "paused": False}
        if hold is not None and hold.source == "owner":
            # The owner lifts the owner's pause: a pause the owner asked for in chat is
            # lifted when the owner asks in chat (P5); the owner's own pause from a control
            # only from a control.
            if not (owner_message and hold.source_message_id is not None):
                raise LonoraError("supervision_resume_not_yours", 403)
        elif hold is None:
            # The agent's own pause: only it lifts it.
            raise LonoraError("supervision_resume_not_yours", 403)
        elif hold.holder_agent_id != actor_id and (
            not owner_message or actor_id == await personal_agent_id(session, owner_id)
        ):
            # Lonora lifts only the pauses Lonora made (4.7.2).
            raise LonoraError("supervision_resume_not_yours", 403)
        await release_hold(
            session,
            hold,
            "holder" if hold.source != "owner" and hold.holder_agent_id == actor_id else "owner",
        )
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
