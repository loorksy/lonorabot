from fastapi import APIRouter, Depends, Request
from lonora_auth.devices import (
    begin_activation,
    begin_enrollment,
    devices,
    finish_activation,
    finish_enrollment,
    relying_party,
)
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.super_bot import (
    DeviceEnrollment,
    DeviceProof,
    SuperBotControl,
    SuperBotProposal,
)
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow, SuperBotRequestRow
from lonora_db.super_bot import (
    authority_lock,
    changed,
    owned_request,
    propose,
    request_data,
    stop_request,
)
from lonora_db.transactions import owned_agent
from sqlalchemy import func, select

from ..device_metadata import native_origins
from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/auth/devices/config")
async def configuration(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    settings = runtime(request).settings
    return {
        "rp_id": relying_party(settings.allowed_origin),
        "android_configured": bool(settings.passkey_android_fingerprints),
        "ios_configured": bool(settings.passkey_ios_app_ids),
    }


@router.get("/auth/devices")
async def list_devices(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return [
            {"id": device.id, "name": device.name, "created_at": device.created_at.isoformat()}
            for device in await devices(session, owner.id)
        ]


@router.post("/auth/devices/enrollment")
async def enrollment(
    request: Request, body: DeviceEnrollment, owner: OwnerIdentity = Depends(require_owner)
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return await begin_enrollment(session, owner, body, rt.settings.allowed_origin)


@router.post("/auth/devices/enrollment/verify")
async def enroll_verify(
    request: Request, body: DeviceProof, owner: OwnerIdentity = Depends(require_owner)
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return await finish_enrollment(
            session, owner, body, rt.settings.allowed_origin, native_origins(rt.settings)
        )


@router.delete("/auth/devices/{device_id}")
async def revoke(request: Request, device_id: str, owner: OwnerIdentity = Depends(require_owner)):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        await authority_lock(session, owner.id + ":devices")
        device = next(
            (item for item in await devices(session, owner.id) if item.id == device_id), None
        )
        if device is None:
            raise LonoraError("device_not_found", 404)
        device.revoked = True
        rows = list(
            await session.scalars(
                select(SuperBotRequestRow)
                .where(
                    SuperBotRequestRow.owner_id == owner.id,
                    SuperBotRequestRow.device_id == device.id,
                    SuperBotRequestRow.status == "activated",
                )
                .order_by(SuperBotRequestRow.goal_id)
            )
        )
        for row in rows:
            await stop_request(session, row, "disabled")
    return {"revoked": True}


@router.get("/agents/{agent_id}/super-bot")
async def state(request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        # The original persisted request time anchors its card among messages.
        # One correlated query avoids N+1 reads and never uses mutable status time.
        anchor = (
            select(func.coalesce(func.max(MessageRow.seq), 0) + 1)
            .where(
                MessageRow.thread_id == SuperBotRequestRow.thread_id,
                MessageRow.created_at <= SuperBotRequestRow.created_at,
            )
            .correlate(SuperBotRequestRow)
            .scalar_subquery()
        )
        rows = await session.execute(
            select(SuperBotRequestRow, anchor)
            .where(SuperBotRequestRow.owner_id == owner.id, SuperBotRequestRow.agent_id == agent_id)
            .order_by(SuperBotRequestRow.created_at.desc())
            .limit(20)
        )
        return [request_data(row, timeline_seq=int(seq)) for row, seq in rows]


@router.post("/agents/{agent_id}/super-bot/proposals", status_code=201)
async def proposal(
    request: Request,
    agent_id: str,
    body: SuperBotProposal,
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        return request_data(await propose(session, owner.id, agent_id, body))


@router.post("/super-bot/{request_id}/challenge")
async def activation(
    request: Request, request_id: str, owner: OwnerIdentity = Depends(require_owner)
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return await begin_activation(session, owner, request_id, rt.settings.allowed_origin)


@router.post("/super-bot/verify")
async def activate_verify(
    request: Request, body: DeviceProof, owner: OwnerIdentity = Depends(require_owner)
):
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        return request_data(
            await finish_activation(
                session, owner, body, rt.settings.allowed_origin, native_origins(rt.settings)
            )
        )


@router.post("/super-bot/control")
async def control(
    request: Request, body: SuperBotControl, owner: OwnerIdentity = Depends(require_owner)
):
    from lonora_db.trading_goals import owned_goal, update_goal_state

    async with runtime(request).db.sessions() as session, session.begin():
        row = await owned_request(session, owner.id, body.request_id)
        await authority_lock(session, row.agent_id)
        goal = await owned_goal(session, owner.id, row.goal_id, True)
        row = await owned_request(session, owner.id, row.id, lock=True)
        if body.action == "reject" and row.status == "pending":
            row.status = "rejected"
            changed(session, row)
        elif body.action in {"stop", "pause"}:
            await stop_request(session, row, "disabled" if body.action == "stop" else "paused")
        elif row.status == "activated" and body.action in {"advisory", "supervised"}:
            ranks = {"advisory": 0, "supervised": 1, "autonomous": 2}
            if ranks[body.action] > ranks[row.mode]:
                raise LonoraError("super_bot_authority_expansion", 403)
            row.mode = body.action
            update_goal_state(session, goal, {**goal.state, "autonomous": False})
            changed(session, row)
        else:
            raise LonoraError("super_bot_transition_invalid", 409)
        return request_data(row)
