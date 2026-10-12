from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_market.broker import broker_market

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/market")


@router.get("/instruments")
async def instruments(
    request: Request, account_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    provider = await broker_market(
        runtime(request).services(owner.id).brokers, owner.id, account_id
    )
    return [item.model_dump(mode="json") for item in await provider.instruments()]


@router.get("/quote")
async def quote(
    request: Request, account_id: str, symbol: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    provider = await broker_market(
        runtime(request).services(owner.id).brokers, owner.id, account_id
    )
    return (await provider.quote(symbol)).model_dump(mode="json")


@router.get("/candles")
async def candles(
    request: Request,
    account_id: str,
    symbol: str,
    timeframe: str = "1h",
    limit: int = Query(default=300, ge=1, le=1000),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    provider = await broker_market(
        runtime(request).services(owner.id).brokers, owner.id, account_id
    )
    return [
        item.model_dump(mode="json") for item in await provider.candles(symbol, timeframe, limit)
    ]
