"""The agent's trading mode at the execution door (mandate 4.1, 4.2.3, 6.7).

Full sends on its own. Ask lets a risk-reducing request through and sends a
risk-increasing one only when it is the exact request of an approved Trade Approval
(``operation_id`` plus ``trade_fingerprint``). Read-only analysis has no dependency on this
gate. Broker reconciliation and committed receipts do not pass through it.
"""

from lonora_contracts.account import Order, Position
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import effective_permission
from lonora_db.schema import RunRow, TradeApprovalRow
from lonora_db.trading_mode import trading_mode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import provisional_voice, ticket_agent
from .admission import may_reduce_risk
from .idempotency import trade_fingerprint


async def require_operation_permission(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    account_authority_id: str | None,
    *,
    reducing: bool | None = None,
    target: Position | Order | None = None,
) -> None:
    """Recheck the agent's current mode and the actual stored approval.

    The caller takes the per-agent authority lock before the final send check, the lock
    every mode change takes. ``reducing`` is the door's own classification of the request
    against the broker's current ticket (``lonora_trading.admission.risk_reducing``);
    None before the ticket is read, when the decisive check at send still follows.
    ``target`` is that ticket (None: the broker no longer shows it).

    A request on a ticket the agent's own journaled order did not open (the owner's own
    position, or another agent's) needs the owner's exact approval in either mode. Under
    an active grant the grant's own terms decide instead, until grants are removed.
    """
    foreign = bool(request.position_id or request.order_id) and reducing is not None
    if foreign:
        foreign = target is None or (
            await ticket_agent(session, owner_id, request, target) != run.agent_id
        )
    if await trading_mode(session, owner_id, run.agent_id) == "full":
        if not foreign:
            return
    elif (level := await effective_permission(session, owner_id, run.agent_id)) == "analysis":
        # Until the permission ladder is removed, "No trading" still refuses in Ask.
        raise LonoraError("agent_analysis_only", 403)
    elif account_authority_id:
        if level != "autonomous":
            raise LonoraError("trade_approval_required", 403)
        if not await provisional_voice(session, run):
            return
        # Provisional speech retains the existing exact-operation confirmation
        # boundary as well as the current signed account scope.
    elif not foreign and (reducing or (reducing is None and may_reduce_risk(request))):
        # Ask: a risk-reducing request on the agent's own ticket needs no approval (4.1).
        return
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
