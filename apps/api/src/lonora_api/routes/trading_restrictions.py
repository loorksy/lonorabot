"""Owner restrictions: create, inspect and lift. Lifting is an owner-session action only.

Agents can create (narrowing) and list restrictions through their own tools; no agent
tool or model call can revoke one. The executor enforces restrictions at the send
boundary (lonora_trading.restrictions).
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.trading_restrictions import RestrictionRevoke, TradingRestrictionCreate
from lonora_db.trading_restrictions import (
    create_restriction,
    list_restrictions,
    restriction_data,
    revoke_restriction,
)

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/trading/restrictions")


@router.get("")
async def restrictions(
    request: Request,
    account_id: str | None = None,
    include_ended: bool = False,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [
            restriction_data(row)
            for row in await list_restrictions(
                session, owner.id, account_id=account_id, include_ended=include_ended, limit=200
            )
        ]


@router.post("", status_code=201)
async def create(
    request: Request, body: TradingRestrictionCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    symbol = body.symbol
    if symbol is not None:
        from lonora_tools.symbols import canonical_broker_symbol

        try:
            broker = await rt.services(owner.id).brokers.get(owner.id, body.account_id)
        except Exception:
            broker = None  # Matching is case-insensitive; an exact spelling is best effort.
        if broker is not None:
            symbol = await canonical_broker_symbol(broker, symbol)
    async with rt.db.sessions() as session, session.begin():
        row = await create_restriction(
            session,
            owner.id,
            account_id=body.account_id,
            agent_id=body.agent_id,
            symbol=symbol,
            action_class=body.action_class,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
            reason=body.reason,
            source="owner_ui",
            created_by_agent_id=None,
            applies_to_owner_manual=body.applies_to_owner_manual,
        )
        return restriction_data(row)


@router.post("/{restriction_id}/revoke")
async def revoke(
    request: Request,
    restriction_id: str,
    body: RestrictionRevoke,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await revoke_restriction(session, owner.id, restriction_id, body.reason)
        return restriction_data(row)
