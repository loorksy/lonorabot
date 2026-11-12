"""The execution door's authority check (mandate 4.1, 4.2.3, 3.3.4, 3.1.3, 6.7).

- An agent in Full sends on its own; an agent in Ask sends a risk-increasing request only
  when it is the exact request of an approved Trade Approval (``operation_id`` plus
  ``trade_fingerprint``). Risk-reducing is the door's own classification
  (``lonora_trading.admission.risk_reducing``) against the broker's current ticket.
- A request on a ticket the agent does not own is refused (``ticket_not_owned``) unless
  the agent is Lonora, the run carries the owner's typed message asking for it, or the
  owner gave the agent a standing instruction to manage every position.
- A risk-increasing request Lonora sends on a ticket owned by an agent in Ask needs the
  exact approval, even when Lonora is in Full.
- A paused agent sends only risk-reducing requests (4.7.1), whatever its mode.

Until grants and the permission ladder are deleted (0.4, 14.1.1), their old checks run
here unchanged: a signed grant's path, and "No trading" refusing every mutation.
Read-only analysis has no dependency on this gate; reconciliation and committed receipts
do not pass through it.
"""

from lonora_contracts.account import Order, Position
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import effective_permission
from lonora_db.owner_words import owner_typed_message
from lonora_db.schema import AgentRow, RunRow, TradeApprovalRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import provisional_voice, ticket_agent
from .admission import may_reduce_risk
from .idempotency import trade_fingerprint


async def acting_agent(session: AsyncSession, owner_id: str, agent_id: str) -> AgentRow:
    """The agent row read fresh: its mode and standing instruction as they are now."""
    agent = await session.get(AgentRow, agent_id, populate_existing=True)
    if agent is None or agent.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    return agent


def require_pause_allows(agent: AgentRow, *, reduces: bool) -> None:
    """A paused agent may send only risk-reducing requests (4.7.1). It reads the agent's
    own row, so every path into the door applies it, with or without a run."""
    if agent.paused and not reduces:
        raise LonoraError("agent_paused", 409)


async def owner_asked(session: AsyncSession, run: RunRow, owner_message_id: str | None) -> bool:
    """Whether ``owner_message_id`` is the owner's typed message this run answers."""
    if owner_message_id is None:
        return False
    message = await owner_typed_message(session, run)
    return message is not None and str(message.id) == owner_message_id


async def require_operation_permission(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    account_authority_id: str | None,
    *,
    reducing: bool | None = None,
    target: Position | Order | None = None,
    owner_message_id: str | None = None,
) -> None:
    """The caller takes the per-agent authority lock before the final send check, the lock
    every mode change takes. ``reducing`` and ``target`` are the door's classification and
    the broker's current ticket; both are None before the ticket is read, when the
    decisive check at send still follows."""
    level = await effective_permission(session, owner_id, run.agent_id)
    if level == "analysis":
        raise LonoraError("agent_analysis_only", 403)
    agent = await acting_agent(session, owner_id, run.agent_id)
    reduces = bool(reducing) or (reducing is None and may_reduce_risk(request))
    require_pause_allows(agent, reduces=reduces)
    if account_authority_id:
        # A signed grant's old path, unchanged until grants are deleted.
        if level != "autonomous":
            raise LonoraError("trade_approval_required", 403)
        if not await provisional_voice(session, run):
            return
        await require_exact_approval(session, owner_id, run, request)
        return
    on_ask_agents_ticket = False
    if (request.position_id or request.order_id) and reducing is not None:
        holder = await ticket_agent(session, owner_id, request, target) if target else None
        if target is None or holder != run.agent_id:
            if agent.role == "personal":
                # Lonora's lead exception; an Ask agent's ticket still asks for new risk.
                if holder is not None:
                    owner_agent = await session.get(AgentRow, holder, populate_existing=True)
                    on_ask_agents_ticket = (
                        owner_agent is not None and owner_agent.trading_mode != "full"
                    )
            elif not (
                agent.manages_all_positions or await owner_asked(session, run, owner_message_id)
            ):
                raise LonoraError("ticket_not_owned", 403)
    if reduces:
        return  # Risk-reducing needs no approval in either mode (4.1).
    if agent.trading_mode == "full" and not on_ask_agents_ticket:
        return
    await require_exact_approval(session, owner_id, run, request)


async def require_exact_approval(
    session: AsyncSession, owner_id: str, run: RunRow, request: TradeRequest
) -> None:
    """The exact-approval match (6.7): ``operation_id`` plus ``trade_fingerprint`` against
    an approved Trade Approval of this run."""
    approvals = await session.scalars(
        select(TradeApprovalRow)
        .where(
            TradeApprovalRow.owner_id == owner_id,
            TradeApprovalRow.agent_id == run.agent_id,
            TradeApprovalRow.run_id == run.id,
            TradeApprovalRow.status == "approved",
        )
        .execution_options(populate_existing=True)
    )
    for approval in approvals:
        if any(
            TradeRequest.model_validate(item).operation_id == request.operation_id
            and trade_fingerprint(TradeRequest.model_validate(item)) == trade_fingerprint(request)
            for item in approval.requests
        ):
            return
    raise LonoraError("trade_approval_required", 403)
