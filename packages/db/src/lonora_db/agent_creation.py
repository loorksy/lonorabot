"""Persistent agents created from the conversation: the one creation service.

``create_root_agent`` is what ``agent_create`` and the owner's creation card run. It
creates an independent root agent through ``agents.create_agent`` (the owner's form
uses the same function): scope ``flexible``, role ``specialist`` with a focus pair and
``general`` without one. It never creates a grant. The ladder is written explicitly:
the trading template starts at "Ask me" (every trade waits for the owner's tap) and
every other template at "No trading", whatever the contract default becomes.

Provenance (who created it, from which owner message, run or card) is kept in the
agent's origin record and in the ``agent.created`` event. The origin record also holds
the agents it reports to: that is the peer link the directory shows. The agents it
supervises get supervision grants with the creation's source (``lonora_db.supervision``).

Limits: at most ``MAXIMUM_ACTIVE_AGENTS`` active (not paused) persistent agents per
owner and ``MAXIMUM_CREATIONS_PER_RUN`` creations or creation cards per run. Undo
deletes an agent that has done nothing yet and pauses one that has (agent deletion
still cascades its work in Wave 1, so it never deletes work).
"""

from hashlib import sha256
from typing import Any, Literal, cast

from lonora_contracts.agent_creation import TEMPLATE_LEVEL, AgentTemplate
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.model_routing import AgentModelChange, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .agents import agent_data, create_agent
from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import (
    AccountAuthorityRow,
    AgentRow,
    EventRow,
    MarketWatchRow,
    OwnerActionRow,
    RoutineRow,
    RunRow,
    SettingRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
)
from .transactions import owned_agent

MAXIMUM_ACTIVE_AGENTS = 20
MAXIMUM_CREATIONS_PER_RUN = 3
MAXIMUM_DESCRIPTION_CHARS = 280

UndoPlan = Literal["delete", "pause"]


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


async def active_agents(session: AsyncSession, owner_id: str) -> int:
    """Persistent agents that are not paused; temporary helpers do not count."""
    count = await session.scalar(
        select(func.count())
        .select_from(AgentRow)
        .where(
            AgentRow.owner_id == owner_id,
            AgentRow.role != "delegated",
            AgentRow.paused.is_(False),
        )
    )
    return int(count or 0)


async def run_creations(session: AsyncSession, owner_id: str, run_id: str) -> int:
    """Agents this run created plus the creation cards it raised."""
    created = await session.scalar(
        select(func.count())
        .select_from(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.run_id == run_id,
            EventRow.kind == "agent.created",
        )
    )
    proposed = await session.scalar(
        select(func.count())
        .select_from(OwnerActionRow)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.run_id == run_id,
            OwnerActionRow.kind == "create_agent",
        )
    )
    return int(created or 0) + int(proposed or 0)


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


async def existing_creation(
    session: AsyncSession, owner_id: str, template: str, name: str
) -> AgentRow | None:
    """The persistent agent already created from this template under this name, if any:
    the owner asked twice (a card and a chat message), it exists once."""
    wanted = " ".join(name.split()).casefold()
    rows = await session.scalars(
        select(AgentRow)
        .where(AgentRow.owner_id == owner_id, AgentRow.role != "delegated")
        .order_by(AgentRow.created_at, AgentRow.id)
    )
    for row in rows:
        if row.name.casefold() != wanted:
            continue
        if (await agent_origin(session, owner_id, row.id)).get("template") == template:
            return row
    return None


async def check_creation(
    session: AsyncSession, owner_id: str, spec: dict[str, Any], *, capped: bool = True
) -> None:
    """Re-check a creation against current state: the cap, the agents it reports to and
    the broker connection its focus pair was looked up on. The cap bounds what agents
    create (a run's call or its card); the owner's own form is not capped, as it never was."""
    if capped and await active_agents(session, owner_id) >= MAXIMUM_ACTIVE_AGENTS:
        raise LonoraError("agent_limit_reached", 409)
    for target_id in spec.get("report_to", []):
        target = await owned_agent(session, owner_id, target_id)
        if target.role == "delegated":
            raise LonoraError("agent_report_to_invalid", 422)
    for target_id in spec.get("supervises", []):
        try:
            await owned_agent(session, owner_id, target_id)
        except LonoraError as error:
            raise LonoraError("agent_supervises_missing", 409) from error
    account_id = spec.get("account_id")
    if account_id:
        connection = await BrokerSessionRepository().get(session, owner_id, account_id)
        version = spec.get("connection_version")
        if version is not None and connection.version != version:
            raise LonoraError("broker_connection_changed", 409)


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
    card_id: str | None = None,
) -> tuple[AgentRow, bool]:
    """Create the agent the spec describes, or return it when this id already exists.

    Returns the agent and whether it is new. The caller has validated the spec's shape
    and resolved its market; this re-checks the cap and references under the owner's
    creation lock. Pending creation cards for the same template and name close with it
    (``agent_already_created``), except ``card_id`` being confirmed: answering a card in
    chat, or two agents proposing one agent, never creates a second one.
    """
    from .owner_actions import lock_owner_actions, settle_created_proposals

    # The order every caller takes them in: owner action cards, then creation.
    await lock_owner_actions(session, owner_id)
    await lock_creation(session, owner_id)
    existing = await session.get(AgentRow, agent_id)
    if existing is not None:
        origin = await agent_origin(session, owner_id, agent_id)
        if existing.owner_id != owner_id or not origin:
            raise LonoraError("agent_identity_conflict", 409)
        return existing, False
    await check_creation(session, owner_id, spec, capped=created_via != "owner_ui")
    template = str(spec["template"])
    responsibility = str(spec.get("responsibility") or "").strip()
    account_id, symbol = spec.get("account_id"), spec.get("symbol")
    row = await create_agent(
        session,
        owner_id,
        AgentCreate(
            template=cast(AgentTemplate, template),
            scope_mode="flexible",
            trading_account_id=account_id,
            trading_symbol=symbol,
            name=await available_name(session, owner_id, str(spec["name"])),
            description=responsibility[:MAXIMUM_DESCRIPTION_CHARS],
            instructions=responsibility,
        ),
        agent_id=agent_id,
    )
    from .agent_models import change_agent_model
    from .agent_permissions import initial_permission

    # Never a grant: "Ask me" or "No trading", written so it does not follow a default.
    await initial_permission(session, owner_id, row.id, TEMPLATE_LEVEL[template])
    if spec.get("model"):
        await change_agent_model(
            session,
            owner_id,
            row.id,
            AgentModelChange(primary=ModelSelection.model_validate(spec["model"])),
        )
    origin: dict[str, Any] = {
        "owner_id": owner_id,
        "agent_id": row.id,
        "template": template,
        "created_via": created_via,
        "created_by_agent_id": created_by_agent_id,
        "source_message_id": source_message_id,
        "run_id": run_id,
        "card_id": card_id,
        "report_to": list(spec.get("report_to", [])),
        # The responsibility an agent wrote from the owner's request: while the agent's
        # instructions still hash to it, the context shows them as that agent's
        # writing, never in the system role (``agent_written_instructions``).
        "instructions_sha256": instructions_digest(responsibility),
        "created_at": utcnow().isoformat(),
    }
    session.add(SettingRow(key=origin_key(owner_id, row.id), payload=origin))
    await session.flush()
    from .supervision import grant_supervision

    # Supervision the owner asked for with the agent: the same source as the agent.
    for target_id in spec.get("supervises", []):
        await grant_supervision(
            session,
            owner_id,
            row.id,
            str(target_id),
            via="owner_message" if created_via == "owner_message" else "owner_card",
            created_by_agent_id=created_by_agent_id,
            source_message_id=source_message_id,
        )
    emit(
        session,
        owner_id,
        "agent.created",
        agent_id=row.id,
        # Counted against the run's creations only when the run itself created it; a
        # card it raised already counts.
        run_id=run_id if created_via == "owner_message" else None,
        payload={key: value for key, value in origin.items() if key != "owner_id"},
    )
    await settle_created_proposals(session, owner_id, template, str(spec["name"]), keep=card_id)
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
        "report_to": [],
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


async def undo_plan(session: AsyncSession, owner_id: str, agent_id: str) -> UndoPlan:
    """Delete only an agent that has done nothing yet; pause one that has (a delete
    would cascade its work)."""
    for row_type in (RunRow, MarketWatchRow, RoutineRow, TicketRow):
        if await session.scalar(select(exists().where(row_type.agent_id == agent_id))):
            return "pause"
    for row_type in (AccountAuthorityRow, TradeApprovalRow):
        if await session.scalar(
            select(exists().where(row_type.owner_id == owner_id, row_type.agent_id == agent_id))
        ):
            return "pause"
    if await session.scalar(
        select(exists().where(AgentRow.owner_id == owner_id, AgentRow.parent_id == agent_id))
    ):
        return "pause"
    return "delete"


async def delete_agent(
    session: AsyncSession, owner_id: str, agent_id: str, *, keep_card: str | None = None
) -> None:
    """The owner's delete: refused while its trade is uncertain; its grants, approvals
    and cards are settled first, and its financial records outlive it. The Undo card
    of its creation settles too, except ``keep_card`` (the Undo being confirmed) and
    one the owner is tapping right now: that decision takes this agent's lock after the
    card's, so waiting for it here would deadlock; it finds the agent gone instead."""
    from .authority_lock import authority_lock
    from .obligations import prepare_delete
    from .owner_actions import supersede_subject
    from .skill_controls import delete_skill_controls

    await authority_lock(session, agent_id)
    from .management_task import end_management_task

    # Before the agent's row lock: the task's Runs are locked first, as their own work does.
    await end_management_task(session, owner_id, agent_id)
    agent = await owned_agent(session, owner_id, agent_id, lock=True)
    if agent.role == "personal":
        raise LonoraError("personal_agent_cannot_delete", 409)
    await prepare_delete(session, owner_id, agent_id=agent_id)
    await supersede_subject(
        session,
        owner_id,
        "agent_created",
        "agent:" + agent_id,
        "agent_already_removed",
        keep=keep_card,
        skip_locked=True,
    )
    await delete_skill_controls(session, owner_id, agent_id)
    origin = await session.get(SettingRow, origin_key(owner_id, agent_id))
    if origin is not None:
        await session.delete(origin)
    from .pauses import owner_holds_for

    # Every pause it holds on other agents' work stays, as the owner's; nothing resumes.
    await owner_holds_for(session, owner_id, agent_id)
    await session.delete(agent)


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
    # The owner's Undo: a supervisor's hold on this agent becomes the owner's pause.
    await owner_takes_over(session, owner_id, "agent", agent_id, paused=True, agent_id=agent_id)
    if not agent.paused:
        agent.paused = True
        emit(session, owner_id, "agent.updated", agent_id=agent_id, payload=agent_data(agent))
    return agent


# The run that tells the proposing agent its card was tapped (server-written prompt).
FIRST_TASK_TRIGGER = "agent_created"


def first_task_run_id(card_id: str) -> str:
    return stable_id(card_id, "first-task")


def first_task_prompt(agent_id: str) -> str:
    """Fixed text and a server id only: the new agent's (model-chosen) name stays out."""
    return (
        f"The owner tapped Create agent on your card: the new agent (agent_id={agent_id}) "
        "exists now and has no task yet. Give it its first task with peer_send, from what "
        "you proposed it for, then tell the owner in one line what it will do."
    )


async def start_first_task(
    session: AsyncSession, card: OwnerActionRow, created: AgentRow
) -> RunRow | None:
    """After the owner tapped Create agent, the agent that proposed it gets one run in the
    card's conversation to hand the new agent its first task. One per card; none when
    the proposing agent is gone or paused (the new agent then waits for the owner)."""
    from lonora_contracts.runs import RunRequest

    from .runs import create_run
    from .threads import conversation_thread

    owner_id = card.owner_id
    run_id = first_task_run_id(card.id)
    if await session.get(RunRow, run_id) is not None:
        return None
    proposer = await session.get(AgentRow, card.agent_id)
    if (
        proposer is None
        or proposer.owner_id != owner_id
        or proposer.paused
        or proposer.role == "delegated"
        or proposer.id == created.id
    ):
        return None
    thread = await session.get(ThreadRow, card.thread_id) if card.thread_id else None
    if (
        thread is None
        or thread.owner_id != owner_id
        or thread.purpose != "conversation"
        or thread.agent_id != proposer.id
        or thread.group_id
    ):
        thread = await conversation_thread(session, owner_id, proposer.id)
    return await create_run(
        session,
        owner_id,
        RunRequest(
            thread_id=thread.id,
            agent_id=proposer.id,
            trigger=FIRST_TASK_TRIGGER,
            prompt=first_task_prompt(created.id),
            metadata={"created_agent_id": created.id, "owner_action_id": card.id},
        ),
        run_id,
    )


async def cancel_first_task(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """Undo before the proposing agent's first-task run started: it never starts."""
    from .cancellation import cancel_run

    card_id = (await agent_origin(session, owner_id, agent_id)).get("card_id")
    if not card_id:
        return
    run = await session.get(RunRow, first_task_run_id(str(card_id)))
    if run is not None and run.status == "queued":
        await cancel_run(session, owner_id, run.id)


def report_targets(origin: dict[str, Any]) -> list[str]:
    """The agents an origin record says this agent reports to: its peer links."""
    value = origin.get("report_to")
    return [str(item) for item in cast(list[Any], value)] if isinstance(value, list) else []
