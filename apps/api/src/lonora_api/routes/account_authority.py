"""Owner-authenticated proposals; only signed user verification activates authority."""

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.account_authority import begin_activation, finish_activation
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.account_authority import AccountAuthorityProposal
from lonora_contracts.super_bot import DeviceProof
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import authority_data, propose, revoke
from lonora_db.schema import AccountAuthorityRow
from lonora_db.transactions import owned_agent
from sqlalchemy import select

from ..device_metadata import native_origins
from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/agents/{agent_id}/account-authorities")
async def state(request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        rows = await session.scalars(
            select(AccountAuthorityRow)
            .where(
                AccountAuthorityRow.owner_id == owner.id,
                AccountAuthorityRow.agent_id == agent_id,
            )
            .order_by(AccountAuthorityRow.created_at.desc())
            .limit(20)
        )
        return [authority_data(row) for row in rows]


@router.post("/agents/{agent_id}/account-authorities", status_code=201)
async def proposal(
    request: Request,
    agent_id: str,
    body: AccountAuthorityProposal,
    owner: OwnerIdentity = Depends(require_owner),
    permission_revision: int | None = Query(default=None, ge=0),
):
    rt = runtime(request)
    async with rt.db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
    if body.symbol_scope == "selected":
        broker = await rt.services(owner.id).brokers.get(owner.id, body.account_id)
        symbols = set(await broker.symbols())
        if any(symbol not in symbols for symbol in body.symbols):
            raise LonoraError("symbol_not_found", 404)
    async with rt.db.sessions() as session, session.begin():
        return authority_data(
            await propose(
                session,
                owner.id,
                agent_id,
                body,
                permission_revision=permission_revision,
            )
        )


@router.post("/account-authorities/{identifier}/challenge")
async def challenge(
    request: Request,
    identifier: str,
    owner: OwnerIdentity = Depends(require_owner),
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return await begin_activation(session, owner, identifier, rt.settings.allowed_origin)


@router.post("/account-authorities/verify")
async def verify(
    request: Request,
    body: DeviceProof,
    owner: OwnerIdentity = Depends(require_owner),
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return authority_data(
            await finish_activation(
                session, owner, body, rt.settings.allowed_origin, native_origins(rt.settings)
            )
        )


@router.post("/account-authorities/{identifier}/revoke")
async def stop(request: Request, identifier: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session, session.begin():
        return authority_data(await revoke(session, owner.id, identifier))
