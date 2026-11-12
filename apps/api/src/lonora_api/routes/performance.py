"""An agent's results per judgment label, from broker-confirmed closes (5.5.4)."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.execution_quality import PerformanceRead
from lonora_db.agent_binding import assert_market_binding
from lonora_db.transactions import owned_agent

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/performance")
async def performance(
    request: Request,
    agent_id: str,
    account_id: str | None = None,
    symbol: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
):
    from lonora_trading.performance import performance_snapshot

    db = runtime(request).db
    async with db.sessions() as session:
        agent = await owned_agent(session, owner.id, agent_id)
        assert_market_binding(agent, account_id, symbol)
        params = PerformanceRead(
            account_id=account_id or agent.trading_account_id,
            symbol=symbol
            or (
                agent.trading_symbol
                if not account_id or account_id == agent.trading_account_id
                else None
            ),
        )
    return await performance_snapshot(db, owner.id, agent_id, params)
