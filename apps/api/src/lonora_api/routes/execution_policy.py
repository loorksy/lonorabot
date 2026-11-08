"""Owner-authenticated policy configuration; never accepted from a model/tool call.

Lowering or adding a money limit is one owner request. Raising or removing one (or
anything else ``widens`` counts as admitting more risk) needs the owner's passkey: the
challenge binds the exact new policy, and ``/verify`` stores exactly that policy once the
assertion is verified, the same ceremony as a limits card in the conversation.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.devices import begin_bound_assertion, verify_bound_assertion
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionSnapshot, ExposureSnapshot
from lonora_contracts.risk_limits import RiskAssessment
from lonora_contracts.super_bot import DeviceProof
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.owner_actions import account_policy, widens
from lonora_db.super_bot import authority_lock
from lonora_session.idempotency import request_hash
from lonora_trading.execution_quality import execution_policy
from lonora_trading.exposure import account_exposure
from lonora_trading.owner_controls import require_account_currency, store_execution_policy
from lonora_trading.risk_limits import assess_risk, risk_operations
from sqlalchemy.ext.asyncio import AsyncSession

from ..device_metadata import native_origins
from ..middleware.auth import require_owner, runtime

# The device-challenge kind for a signed policy change (at most 16 characters).
POLICY_CHALLENGE = "execution_policy"


class SignedExecutionPolicy(Contract):
    """A money-limit widening: the exact policy and the passkey assertion bound to it."""

    policy: ExecutionPolicy
    proof: DeviceProof


def policy_binding(account_id: str, policy: ExecutionPolicy) -> str:
    return request_hash({"account_id": account_id, "policy": policy.model_dump(mode="json")})


async def widening(
    session: AsyncSession, owner_id: str, account_id: str, policy: ExecutionPolicy
) -> bool:
    """Whether the new policy admits more money risk than the account's current one.

    Read under the account lock the store takes, so the judgement matches what it replaces.
    """
    await BrokerSessionRepository().get(session, owner_id, account_id, lock=True)
    return widens((await account_policy(session, owner_id, account_id)).risk, policy.risk)


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
        if await widening(session, owner.id, account_id, body):
            # Raising or removing a money limit widens what may be lost: passkey only.
            raise LonoraError("execution_policy_passkey_required", 403)
        await store_execution_policy(session, owner.id, account_id, body)
    return body


@router.post("/execution-policy/challenge")
async def policy_challenge(
    request: Request,
    account_id: str,
    body: ExecutionPolicy,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Passkey options bound to this exact policy; only a widening needs one."""
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        await authority_lock(session, owner.id + ":devices")
        if not await widening(session, owner.id, account_id, body):
            raise LonoraError("execution_policy_passkey_not_needed", 409)
        return await begin_bound_assertion(
            session,
            owner,
            POLICY_CHALLENGE,
            account_id,
            policy_binding(account_id, body),
            rt.settings.allowed_origin,
        )


@router.post("/execution-policy/verify")
async def signed_policy(
    request: Request,
    account_id: str,
    body: SignedExecutionPolicy,
    owner: OwnerIdentity = Depends(require_owner),
) -> ExecutionPolicy:
    """Store exactly the policy the owner's verified assertion signed."""
    rt = runtime(request)
    await require_account_currency(
        rt.services(owner.id).brokers, owner.id, account_id, body.policy.risk.currency
    )
    async with rt.db.sessions() as session, session.begin():
        # The order the challenge takes them in: the owner's devices, then the account.
        await authority_lock(session, owner.id + ":devices")
        await BrokerSessionRepository().get(session, owner.id, account_id, lock=True)
        await verify_bound_assertion(
            session,
            owner,
            body.proof,
            POLICY_CHALLENGE,
            account_id,
            policy_binding(account_id, body.policy),
            rt.settings.allowed_origin,
            native_origins(rt.settings),
        )
        await store_execution_policy(session, owner.id, account_id, body.policy)
    return body.policy


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
