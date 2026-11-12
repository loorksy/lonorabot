"""Owner action cards raised and settled from runtime events, with no model involved.

The attention projection hands every event it reads to ``follow_event`` before deciding
the owner's notification: an operation that becomes ambiguous raises a three-button
resolve card in the responsible agent's conversation (Lonora's for the owner's own
orders), and cards whose record moved on are settled (a settled operation). Raising is
idempotent per record.
"""

from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_db.owner_actions import raise_system_card, supersede_subject
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import AgentRow, EventRow, TradingJournalRow
from sqlalchemy.ext.asyncio import AsyncSession

CARD_EVENTS = frozenset(
    {
        "trading.operation_updated",
    }
)


async def card_agent(session: AsyncSession, owner_id: str, agent_id: str | None) -> str:
    """The agent the card is about, or Lonora when there is none (or it was deleted)."""
    agent = await session.get(AgentRow, agent_id) if agent_id else None
    if agent is not None and agent.owner_id == owner_id:
        return agent.id
    return (await ensure_personal_agent(session, owner_id)).id


async def follow_event(session: AsyncSession, event: EventRow) -> None:
    if event.kind not in CARD_EVENTS:
        return
    owner_id = event.owner_id
    if event.kind == "trading.operation_updated":
        operation = await session.get(
            TradingJournalRow, str(event.payload.get("operation_id") or "")
        )
        if operation is None or operation.owner_id != owner_id:
            return
        subject = "operation:" + operation.operation_id
        if operation.status == "ambiguous":
            agent_id = await card_agent(session, owner_id, event.agent_id)
            await raise_system_card(
                session,
                owner_id,
                OwnerActionProposal(kind="resolve_operation", operation_id=operation.operation_id),
                agent_id=agent_id,
                thread_id=event.thread_id if agent_id == event.agent_id else None,
                run_id=event.run_id,
            )
        elif operation.status not in UNRESOLVED_STATUSES:
            await supersede_subject(
                session, owner_id, "resolve_operation", subject, "operation_already_settled"
            )
        return
