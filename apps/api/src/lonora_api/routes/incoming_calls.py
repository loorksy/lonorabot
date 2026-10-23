"""Authenticated owner invitation signaling. Push payloads cannot accept calls."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.incoming_calls import IncomingCallAction, IncomingCallPolicy
from lonora_db.schema import VoiceSessionRow
from lonora_voice.incoming import (
    MODE,
    call_data,
    incoming_tick,
    preferences,
    set_preferences,
    transition,
)
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/voice/incoming")


@router.get("/policy")
async def get_policy(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return (await preferences(session, owner.id)).model_dump(mode="json")


@router.put("/policy")
async def update_policy(
    request: Request, body: IncomingCallPolicy, owner: OwnerIdentity = Depends(require_owner)
):
    async with runtime(request).db.sessions() as session, session.begin():
        await set_preferences(session, owner.id, body)
    return body.model_dump(mode="json")


@router.get("")
async def current(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    db = runtime(request).db
    await incoming_tick(db, owner.id)
    async with db.sessions() as session:
        rows = await session.scalars(
            select(VoiceSessionRow)
            .where(
                VoiceSessionRow.owner_id == owner.id,
                VoiceSessionRow.payload["mode"].as_string() == MODE,
                VoiceSessionRow.payload["status"].as_string() == "ringing",
            )
            .order_by(VoiceSessionRow.created_at.desc())
            .limit(20)
        )
        return [call_data(row) for row in rows]


@router.post("/{identifier}/respond")
async def respond(
    request: Request,
    identifier: str,
    body: IncomingCallAction,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return call_data(
            await transition(session, owner.id, identifier, body.action, body.device_id)
        )
