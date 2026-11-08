"""Persistent agents created from the conversation: the one creation service.

``create_root_agent`` is what ``agent_create`` and the owner's creation card run. It
creates an independent root agent through ``agents.create_agent`` (the owner's form
uses the same function): scope ``flexible``, role ``specialist`` with a focus pair and
``general`` without one. It never creates a grant. The ladder is written explicitly:
the trading template starts at "Ask me" (every trade waits for the owner's tap) and
every other template at "No trading", whatever the contract default becomes.

Provenance (who created it, from which owner message, run or card) is kept in the
agent's origin record and in the ``agent.created`` event. The origin record also holds
the agents it reports to: that is the peer link the directory shows.

Limits: at most ``MAXIMUM_ACTIVE_AGENTS`` active (not paused) persistent agents per
owner and ``MAXIMUM_CREATIONS_PER_RUN`` creations or creation cards per run. Undo
deletes an agent that has done nothing yet and pauses one that has (agent deletion
still cascades its work in Wave 1, so it never deletes work).
"""

from hashlib import sha256
from typing import Any, Literal, cast

from lonora_contracts.agent_creation import TEMPLATE_LEVEL
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.model_routing import AgentModelChange, ModelSelection
from lonora_core.user_error import LonoraError
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


async def check_creation(session: AsyncSession, owner_id: str, spec: dict[str, Any]) -> None:
    """Re-check a creation against current state: the cap, the agents it reports to and
    the broker connection its focus pair was looked up on."""
    if await active_agents(session, owner_id) >= MAXIMUM_ACTIVE_AGENTS:
        raise LonoraError("agent_limit_reached", 409)
    for target_id in spec.get("report_to", []):
        target = await owned_agent(session, owner_id, target_id)
        if target.role == "delegated":
            raise LonoraError("agent_report_to_invalid", 422)
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
    creation lock.
    """
    await lock_creation(session, owner_id)
    existing = await session.get(AgentRow, agent_id)
    if existing is not None:
        origin = await agent_origin(session, owner_id, agent_id)
        if existing.owner_id != owner_id or not origin:
            raise LonoraError("agent_identity_conflict", 409)
        return existing, False
    await check_creation(session, owner_id, spec)
    template = str(spec["template"])
    responsibility = str(spec.get("responsibility") or "").strip()
    account_id, symbol = spec.get("account_id"), spec.get("symbol")
    row = await create_agent(
        session,
        owner_id,
        AgentCreate(
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
        "created_at": utcnow().isoformat(),
    }
    session.add(SettingRow(key=origin_key(owner_id, row.id), payload=origin))
    await session.flush()
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
    of its creation settles too, except ``keep_card`` (the Undo being confirmed)."""
    from .obligations import prepare_delete
    from .owner_actions import supersede_subject
    from .skill_controls import delete_skill_controls
    from .super_bot import authority_lock

    await authority_lock(session, agent_id)
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
    )
    await delete_skill_controls(session, owner_id, agent_id)
    origin = await session.get(SettingRow, origin_key(owner_id, agent_id))
    if origin is not None:
        await session.delete(origin)
    await session.delete(agent)


async def pause_agent(session: AsyncSession, owner_id: str, agent_id: str) -> AgentRow:
    """Stop its runs, routines and watches; nothing it did is removed."""
    agent = await owned_agent(session, owner_id, agent_id, lock=True)
    if not agent.paused:
        agent.paused = True
        emit(session, owner_id, "agent.updated", agent_id=agent_id, payload=agent_data(agent))
    return agent


def report_targets(origin: dict[str, Any]) -> list[str]:
    """The agents an origin record says this agent reports to: its peer links."""
    value = origin.get("report_to")
    return [str(item) for item in cast(list[Any], value)] if isinstance(value, list) else []
