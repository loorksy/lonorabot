"""Owner-authenticated policy configuration; never accepted from a model/tool call."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionSnapshot, ExposureSnapshot
from lonora_contracts.risk_limits import RiskAssessment
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_trading.execution_quality import execution_policy
from lonora_trading.exposure import account_exposure
from lonora_trading.owner_controls import require_account_currency, store_execution_policy
from lonora_trading.risk_limits import assess_risk, risk_operations

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/trading/accounts/{account_id}")


@router.get("/execution-policy")
async def read_policy(
    request: Request, account_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> ExecutionPolicy:
    db = runtime(request).db
    async with db.sessions() as session:
        await BrokerSessionRepository().get(session, owner.id, account_id)
    return await execution_policy(db, owner.id, account_id)


@router.put("/execution-policy")
async def write_policy(
    request: Request,
    account_id: str,
    body: ExecutionPolicy,
    owner: OwnerIdentity = Depends(require_owner),
) -> ExecutionPolicy:
    rt = runtime(request)
    await require_account_currency(
        rt.services(owner.id).brokers, owner.id, account_id, body.risk.currency
    )
    async with rt.db.sessions() as session, session.begin():
        await store_execution_policy(session, owner.id, account_id, body)
    return body


@router.get("/risk-status")
async def risk_status(
    request: Request, account_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> RiskAssessment:
    """Current book against the owner's monetary limits; read-only, authorizes nothing."""
    rt = runtime(request)
    policy = await execution_policy(rt.db, owner.id, account_id)
    broker = await rt.services(owner.id).brokers.get(owner.id, account_id)
    account = await broker.account()
    account.id = account_id
    snapshot = ExecutionSnapshot(
        account=account,
        positions=await broker.positions(),
        orders=await broker.orders(),
        observed_at=utcnow(),
    )
    async with rt.db.sessions() as session:
        operations = await risk_operations(session, owner.id, account_id)
    return await assess_risk(
        broker, None, snapshot, policy.risk, reducing=False, operations=operations
    )


@router.get("/exposure")
async def exposure(
    request: Request, account_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> ExposureSnapshot:
    rt = runtime(request)
    broker = await rt.services(owner.id).brokers.get(owner.id, account_id)
    account = await broker.account()
    account.id = account_id
    return account_exposure(
        ExecutionSnapshot(
            account=account,
            positions=await broker.positions(),
            orders=await broker.orders(),
            observed_at=utcnow(),
        )
    )
