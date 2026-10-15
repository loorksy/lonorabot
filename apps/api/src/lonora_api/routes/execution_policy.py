"""Owner-authenticated policy configuration; never accepted from a model/tool call."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionSnapshot, ExposureSnapshot
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.transactions import SettingsRepository
from lonora_trading.execution_quality import execution_policy, policy_key
from lonora_trading.exposure import account_exposure

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
    db = runtime(request).db
    async with db.sessions() as session, session.begin():
        await BrokerSessionRepository().get(session, owner.id, account_id, lock=True)
        await SettingsRepository().put(
            session, policy_key(owner.id, account_id), body.model_dump(mode="json")
        )
    return body


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
