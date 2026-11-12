"""Owner-authenticated proposals; only signed user verification activates authority."""

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.account_authority import begin_activation, finish_activation
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.account_authority import ALL_AUTHORITY_ACTIONS, AccountAuthorityProposal
from lonora_contracts.devices import DeviceProof
from lonora_contracts.owner_actions import AccountAuthorityDraft, GrantDraft
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import authority_summary, propose, revoke
from lonora_db.agent_binding import require_financial_agent
from lonora_db.owner_actions import draft_grant_card, full_delegation_available, owner_action_data
from lonora_db.schema import AccountAuthorityRow
from lonora_db.transactions import owned_agent
from lonora_tools.owner_actions import resolve_grant
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
        return [await authority_summary(session, row) for row in rows]


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
        return await authority_summary(
            session,
            await propose(
                session,
                owner.id,
                agent_id,
                body,
                permission_revision=permission_revision,
            ),
        )


@router.post("/agents/{agent_id}/account-authorities/draft", status_code=201)
async def draft(
    request: Request,
    agent_id: str,
    body: AccountAuthorityDraft,
    owner: OwnerIdentity = Depends(require_owner),
):
    """The mandate sheet («تنفيذ مفوَّض», Q17/Q18): the owner's draft becomes a pending
    grant card with the exact payload and its hash. Nothing is active until the owner
    signs it with the passkey: ``POST /owner-actions/{id}/challenge`` then
    ``POST /owner-actions/{id}/decision`` with the proof (and the card's own choices:
    ``money_limit``, ``stop_authorities``)."""
    rt = runtime(request)
    async with rt.db.sessions() as session:
        agent = await require_financial_agent(session, owner.id, agent_id)
        full_available = full_delegation_available(agent)
    # Broker IO (symbols, equity for a percentage) before the transaction.
    resolved = await resolve_grant(
        rt.db, rt.services(owner.id).brokers, owner.id, agent_id, body.proposal(agent_id)
    )
    if body.mode == "full":
        resolved = (
            resolved.with_delegation("full")
            if full_available
            # A fixed-pair agent's «كامل» (Q17): its own pair only, every action, until
            # stopped, the owner's own positions included, no daily loss from the card.
            else GrantDraft.model_validate(
                {
                    **resolved.model_dump(),
                    "actions": list(ALL_AUTHORITY_ACTIONS),
                    "duration": "until_stopped",
                    "allow_manual_positions": True,
                    "daily_loss": None,
                }
            )
        )
    async with rt.db.sessions() as session, session.begin():
        row = await draft_grant_card(session, owner.id, resolved, body.thread_id)
        return {
            "owner_action": await owner_action_data(session, row),
            "payload": row.payload,
            "payload_hash": row.payload_hash,
        }


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
        row = await finish_activation(
            session, owner, body, rt.settings.allowed_origin, native_origins(rt.settings)
        )
        return await authority_summary(session, row)


@router.post("/account-authorities/{identifier}/revoke")
async def stop(request: Request, identifier: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session, session.begin():
        return await authority_summary(session, await revoke(session, owner.id, identifier))
