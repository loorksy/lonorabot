from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.schema import TradingOpportunityRow
from lonora_db.trading_opportunities import opportunity_data, opportunity_history, owned_opportunity
from lonora_trading.opportunities import refresh_opportunity
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/trading/opportunities")


@router.get("")
async def list_items(
    request: Request,
    agent_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        query = select(TradingOpportunityRow).where(TradingOpportunityRow.owner_id == owner.id)
        if agent_id:
            query = query.where(TradingOpportunityRow.agent_id == agent_id)
        rows = list(
            await session.scalars(
                query.order_by(TradingOpportunityRow.updated_at.desc()).limit(limit)
            )
        )
        return [opportunity_data(row) for row in rows]


@router.get("/{identifier}")
async def read(request: Request, identifier: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session, session.begin():
        row = await owned_opportunity(session, owner.id, identifier, lock=True)
        await refresh_opportunity(session, row)
        return {
            **opportunity_data(row),
            "history": await opportunity_history(session, owner.id, identifier),
        }
