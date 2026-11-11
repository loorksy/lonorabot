from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_db.market_watches import (
    MarketWatchRepository,
    control_watch,
    extend_watch,
    restore_expiry,
)
from lonora_db.transactions import resource_data
from pydantic import Field, model_validator

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/watches", MarketWatchRepository())


class WatchControl(Contract):
    action: Literal["cancel", "pause", "resume", "extend", "restore"]
    # extend only: how many hours later the watch ends («تمديد ساعتين» sends 2).
    hours: int | None = Field(default=None, ge=1, le=24)
    # restore only (Undo of an extend): the expiry before it and the revision it left.
    expires_at: datetime | None = None
    revision: int | None = None

    @model_validator(mode="after")
    def fields_for_action(self) -> "WatchControl":
        if (self.action == "extend") != (self.hours is not None):
            raise ValueError("watch_extend_hours_required")
        restore = self.action == "restore"
        if any((value is None) == restore for value in (self.expires_at, self.revision)):
            raise ValueError("watch_restore_fields_required")
        return self


@router.post("/{watch_id}/control")
async def control(
    request: Request,
    watch_id: str,
    body: WatchControl,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """The owner's Cancel, Pause, Resume or Extend on any of their watches; repeating
    Cancel, Pause or Resume is a no-op, each Extend moves the expiry ``hours`` later.
    Restore is the Undo of an Extend: the earlier expiry back while the watch is still at
    the revision that Extend left (``watch_changed_again`` otherwise)."""
    async with runtime(request).db.sessions() as session, session.begin():
        if body.action == "extend":
            assert body.hours is not None
            return resource_data(await extend_watch(session, owner.id, watch_id, body.hours))
        if body.action == "restore":
            assert body.expires_at is not None and body.revision is not None
            return resource_data(
                await restore_expiry(
                    session, owner.id, watch_id, body.expires_at.isoformat(), body.revision
                )
            )
        return resource_data(await control_watch(session, owner.id, watch_id, body.action))
