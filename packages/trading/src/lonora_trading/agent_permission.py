"""Current approval behavior at the existing financial executor boundary.

This is a projection/check over existing grants and operation approvals, never
a second financial authorization engine. Read-only analysis has no dependency
on this gate. Broker reconciliation and committed receipts do not pass through it.
"""

from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import effective_permission
from lonora_db.schema import RunRow, TradeApprovalRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import provisional_voice
from .idempotency import trade_fingerprint


async def require_operation_permission(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    account_authority_id: str | None,
) -> None:
    """Recheck the current Agent selection and actual stored approval.

    The caller takes the existing per-Agent authority lock before the final
    send check. An authorization callback or old Goal grant alone is not proof.
    AccountAuthority scope, device and budgets are validated by the executor's
    existing require_account_execution immediately beside this check.
    """
    level = await effective_permission(session, owner_id, run.agent_id)
    if level == "analysis":
        raise LonoraError("agent_analysis_only", 403)
    if level == "autonomous":
        if not account_authority_id:
            raise LonoraError("account_authority_required", 403)
        if not await provisional_voice(session, run):
            return
        # Provisional speech retains the existing exact-operation confirmation
        # boundary as well as the current signed account scope.
    elif account_authority_id:
        raise LonoraError("trade_approval_required", 403)
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
