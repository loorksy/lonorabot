"""Persistent agents: the one creation service (mandate 3.1.2, 3.3).

``create_root_agent`` is what ``agent_create`` (Lonora's) runs. It creates a flat team
agent through ``agents.create_agent``: no template, no parent, no hierarchy, no binding
to an account or symbol (an instrument or account Lonora assigns is an instruction in
the agent's method, written by ``lonora_agent.collaboration``). It creates no trading or
supervision grant: Lonora leads it by its role. The new agent uses Lonora's current model (12.3: until the owner
assigns another) and starts in the mode its creator resolved (4.3.2, 4.3.3); in Full its
continuous account-management task starts at once (4.5.1).

Provenance (who created it, from which owner message or run) is kept in the agent's
origin record and in the ``agent.created`` event.

Limits: no limit on the number of agents (3.3.2). The one rate guard against a runaway
creation loop is ``MAXIMUM_CREATIONS_PER_RUN`` creations per minute within one run; it
never counts the owner's agents.
"""

from datetime import timedelta
from hashlib import sha256
from typing import Any, cast

from lonora_contracts.domain import AgentCreate, utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .agents import agent_data, create_agent
from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import (
    AgentRow,
    EventRow,
    SettingRow,
    TradeApprovalRow,
)
from .transactions import owned_agent

MAXIMUM_CREATIONS_PER_RUN = 3
# The guard counts one run's creations per minute (3.3.2), never the owner's agents.
CREATION_WINDOW = timedelta(minutes=1)
MAXIMUM_DESCRIPTION_CHARS = 280


def origin_key(owner_id: str, agent_id: str) -> str:
    return "agent-origin:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def instructions_digest(text: str) -> str:
    return sha256(text.strip().encode()).hexdigest()


def agent_written_instructions(origin: dict[str, Any], instructions: str) -> bool:
    """Whether an agent's instructions are still the text another agent wrote when it
    created it (``agent_create``), rather than the owner's own: those are model-authored
    and belong in labelled context data, not the system role. An older record without
    the digest counts as agent-written; the owner editing them makes them the owner's."""
    if not origin.get("created_by_agent_id") or not instructions.strip():
        return False
    digest = origin.get("instructions_sha256")
    return digest is None or digest == instructions_digest(instructions)


async def agent_origin(session: AsyncSession, owner_id: str, agent_id: str) -> dict[str, Any]:
    """How the agent came to exist; empty for agents older than this record."""
    row = await session.get(SettingRow, origin_key(owner_id, agent_id))
    if row is None or row.payload.get("owner_id") != owner_id:
        return {}
    return dict(row.payload)


async def lock_creation(session: AsyncSession, owner_id: str) -> None:
    """Serialize creations per owner, so the cap and the name suffixes hold."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "agent-create:" + owner_id},
        )


async def run_creations(session: AsyncSession, owner_id: str, run_id: str) -> int:
    """Agents this run created in the last ``CREATION_WINDOW``: the guard against a
    runaway creation loop (mandate 3.3.2)."""
    since = utcnow() - CREATION_WINDOW
    created = await session.scalar(
        select(func.count())
        .select_from(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.run_id == run_id,
            EventRow.kind == "agent.created",
            EventRow.created_at >= since,
        )
    )
    return int(created or 0)


async def available_name(session: AsyncSession, owner_id: str, name: str) -> str:
    """The name, or the name with the first free number when another agent has it."""
    taken = {
        value.casefold()
        for value in await session.scalars(
            select(AgentRow.name).where(AgentRow.owner_id == owner_id)
        )
    }
    if name.casefold() not in taken:
        return name
    for number in range(2, 1000):
        suffix = f" {number}"
        candidate = name[: 80 - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
    raise LonoraError("agent_name_unavailable", 409)


async def check_creation(session: AsyncSession, owner_id: str, spec: dict[str, Any]) -> None:
    """Re-check a creation against current state: the broker connection its assigned
    market was looked up on."""
    account_id = spec.get("account_id")
    if account_id:
        connection = await BrokerSessionRepository().get(session, owner_id, account_id)
        version = spec.get("connection_version")
        if version is not None and connection.version != version:
            raise LonoraError("broker_connection_changed", 409)


async def lead_model(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """The new agent uses Lonora's current model (3.1.2, 12.3): a copy of Lonora's choice
    at this moment, attributed to Lonora; nothing when Lonora follows the owner's
    default routes."""
    from .agent_models import apply_agent_model, stored_agent_model
    from .lead import personal_agent_id

    lead = await personal_agent_id(session, owner_id)
    if lead is None or lead == agent_id:
        return
    record = await stored_agent_model(session, owner_id, lead)
    if record.chosen_by is None:
        return
    await apply_agent_model(
        session,
        owner_id,
        agent_id,
        record.state(),
        chosen_by="agent",
        by_agent_id=lead,
        via="lead_creation",
    )


async def create_root_agent(
    session: AsyncSession,
    owner_id: str,
    spec: dict[str, Any],
    *,
    agent_id: str,
    created_via: str,
    created_by_agent_id: str | None,
    source_message_id: str | None,
    run_id: str | None,
) -> tuple[AgentRow, bool]:
    """Create the agent the spec describes, or return it when this id already exists.

    Returns the agent and whether it is new. The caller has validated the spec's shape,
    resolved its market and its mode (``spec["mode"]``, Ask when absent); this re-checks
    the connection under the owner's creation lock.
    """
    from .owner_actions import lock_owner_actions

    # The order every caller takes them in: owner action cards, then creation.
    await lock_owner_actions(session, owner_id)
    await lock_creation(session, owner_id)
    existing = await session.get(AgentRow, agent_id)
    if existing is not None:
        origin = await agent_origin(session, owner_id, agent_id)
        if existing.owner_id != owner_id or not origin:
            raise LonoraError("agent_identity_conflict", 409)
        return existing, False
    await check_creation(session, owner_id, spec)
    responsibility = str(spec.get("responsibility") or "").strip()
    row = await create_agent(
        session,
        owner_id,
        AgentCreate(
            scope_mode="flexible",
            name=await available_name(session, owner_id, str(spec["name"])),
            description=responsibility[:MAXIMUM_DESCRIPTION_CHARS],
            instructions=responsibility,
        ),
        agent_id=agent_id,
    )
    # A team agent has no template (14.2.6): its responsibilities are its method.
    row.template = None
    mode = "full" if spec.get("mode") == "full" else "ask"
    # A new agent: nothing can send for it yet, so no authority lock is held here.
    row.trading_mode = mode
    from .agent_permissions import initial_permission

    # Never a grant and never "No trading" (4.1): the old ladder's "Ask me".
    await initial_permission(session, owner_id, row.id, "supervised")
    await lead_model(session, owner_id, row.id)
    origin: dict[str, Any] = {
        "owner_id": owner_id,
        "agent_id": row.id,
        "template": None,
        "created_via": created_via,
        "created_by_agent_id": created_by_agent_id,
        "source_message_id": source_message_id,
        "run_id": run_id,
        "card_id": None,
        "trading_mode": mode,
        # The responsibility Lonora wrote: while the agent's instructions still hash to
        # it, the context shows them as Lonora's writing, never in the system role
        # (``agent_written_instructions``).
        "instructions_sha256": instructions_digest(responsibility),
        "created_at": utcnow().isoformat(),
    }
    session.add(SettingRow(key=origin_key(owner_id, row.id), payload=origin))
    await session.flush()
    if mode == "full":
        from .management_task import ensure_management_task

        await ensure_management_task(session, owner_id, row.id)
    emit(
        session,
        owner_id,
        "agent.created",
        agent_id=row.id,
        # Counted against the run's creations (the per-run guard).
        run_id=run_id,
        payload={key: value for key, value in origin.items() if key != "owner_id"},
    )
    return row, True


async def record_owner_creation(session: AsyncSession, owner_id: str, row: AgentRow) -> None:
    """The owner's own form: the same provenance record and event, no template."""
    origin: dict[str, Any] = {
        "owner_id": owner_id,
        "agent_id": row.id,
        "template": None,
        "created_via": "owner_ui",
        "created_by_agent_id": None,
        "source_message_id": None,
        "run_id": None,
        "card_id": None,
        "created_at": utcnow().isoformat(),
    }
    session.add(SettingRow(key=origin_key(owner_id, row.id), payload=origin))
    await session.flush()
    emit(
        session,
        owner_id,
        "agent.created",
        agent_id=row.id,
        payload={key: value for key, value in origin.items() if key != "owner_id"},
    )


async def delete_agent(session: AsyncSession, owner_id: str, agent_id: str) -> int:
    """Delete a team agent (by the owner or Lonora): refused while its trade is uncertain;
    its pending Trade Approval cards are withdrawn (3.1.2), its grants, approved requests
    and cards are settled, and its financial records outlive it. Returns how many cards
    were withdrawn."""
    from .authority_lock import authority_lock
    from .obligations import prepare_delete
    from .skill_controls import delete_skill_controls

    await authority_lock(session, agent_id)
    from .management_task import end_management_task

    # Before the agent's row lock: the task's Runs are locked first, as their own work does.
    await end_management_task(session, owner_id, agent_id)
    agent = await owned_agent(session, owner_id, agent_id, lock=True)
    if agent.role == "personal":
        raise LonoraError("personal_agent_cannot_delete", 409)
    from .trade_approvals import approval_event

    # Withdrawn, never approved or executed (10.3.1.3); locked where prepare_delete locks.
    pending = await session.scalars(
        select(TradeApprovalRow)
        .where(
            TradeApprovalRow.owner_id == owner_id,
            TradeApprovalRow.agent_id == agent_id,
            TradeApprovalRow.status == "pending",
        )
        .order_by(TradeApprovalRow.id)
        .with_for_update()
    )
    withdrawn = 0
    for card in pending:
        card.status, card.updated_at = "withdrawn", utcnow()
        approval_event(session, card)
        withdrawn += 1
    await prepare_delete(session, owner_id, agent_id=agent_id)
    await delete_skill_controls(session, owner_id, agent_id)
    origin = await session.get(SettingRow, origin_key(owner_id, agent_id))
    if origin is not None:
        await session.delete(origin)
    from .pauses import owner_holds_for

    # Every pause it holds on other agents' work stays, as the owner's; nothing resumes.
    await owner_holds_for(session, owner_id, agent_id)
    await session.delete(agent)
    return withdrawn


async def pause_agent(session: AsyncSession, owner_id: str, agent_id: str) -> AgentRow:
    """Stop its runs, routines and watches; nothing it did is removed."""
    from .authority_lock import authority_lock
    from .management_task import end_management_task
    from .pauses import owner_takes_over

    await authority_lock(session, agent_id)
    # A paused agent's Full-mode task ends (4.5.2), before the agent's row lock: the
    # task's Runs are locked first, as their own work does.
    await end_management_task(session, owner_id, agent_id)
    agent = await owned_agent(session, owner_id, agent_id, lock=True)
    # The owner's pause: a supervisor's hold on this agent becomes the owner's pause.
    await owner_takes_over(session, owner_id, "agent", agent_id, paused=True, agent_id=agent_id)
    if not agent.paused:
        agent.paused = True
        emit(session, owner_id, "agent.updated", agent_id=agent_id, payload=agent_data(agent))
    return agent


def report_targets(origin: dict[str, Any]) -> list[str]:
    """The peer links an agent created before the flat team recorded (``report_to``); none
    now (3.3.3). Read only to remove those links when such an agent is deleted."""
    value = origin.get("report_to")
    return [str(item) for item in cast(list[Any], value)] if isinstance(value, list) else []
