"""Owner-scoped historical replay; read-only, no new execution endpoint."""

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.trading_decision import TradingDecision
from lonora_db.trading_decisions import decision_history, decision_summary, read_decision

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/trading/decisions")


@router.get("")
async def history(
    request: Request,
    account_id: str | None = None,
    symbol: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session:
        return [
            decision_summary(row)
            for row in await decision_history(
                session,
                owner.id,
                agent_id=agent_id,
                account_id=account_id,
                symbol=symbol,
                limit=limit,
            )
        ]


@router.get("/{decision_id}")
async def read(
    request: Request, decision_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> TradingDecision:
    async with runtime(request).db.sessions() as session:
        return await read_decision(session, owner.id, decision_id)
