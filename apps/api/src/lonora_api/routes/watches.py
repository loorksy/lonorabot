from typing import Any, Literal

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_db.market_watches import MarketWatchRepository, control_watch, extend_watch
from lonora_db.transactions import resource_data
from pydantic import Field, model_validator

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/watches", MarketWatchRepository())


class WatchControl(Contract):
    action: Literal["cancel", "pause", "resume", "extend"]
    # extend only: how many hours later the watch ends («تمديد ساعتين» sends 2).
    hours: int | None = Field(default=None, ge=1, le=24)

    @model_validator(mode="after")
    def hours_for_extend(self) -> "WatchControl":
        if (self.action == "extend") != (self.hours is not None):
            raise ValueError("watch_extend_hours_required")
        return self


@router.post("/{watch_id}/control")
async def control(
    request: Request,
    watch_id: str,
    body: WatchControl,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """The owner's Cancel, Pause, Resume or Extend on any of their watches; repeating
    Cancel, Pause or Resume is a no-op, each Extend moves the expiry ``hours`` later."""
    async with runtime(request).db.sessions() as session, session.begin():
        if body.action == "extend":
            assert body.hours is not None
            return resource_data(await extend_watch(session, owner.id, watch_id, body.hours))
        return resource_data(await control_watch(session, owner.id, watch_id, body.action))
