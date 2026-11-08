from typing import Any, Literal

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_db.market_watches import MarketWatchRepository, control_watch
from lonora_db.transactions import resource_data

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/watches", MarketWatchRepository())


class WatchControl(Contract):
    action: Literal["cancel", "pause", "resume"]


@router.post("/{watch_id}/control")
async def control(
    request: Request,
    watch_id: str,
    body: WatchControl,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """The owner's Cancel, Pause or Resume on any of their watches; repeating is a no-op."""
    async with runtime(request).db.sessions() as session, session.begin():
        return resource_data(await control_watch(session, owner.id, watch_id, body.action))
