from fastapi import APIRouter, Depends, Request
from lonora_auth.devices import (
    begin_enrollment,
    devices,
    finish_enrollment,
    relying_party,
)
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.devices import DeviceEnrollment, DeviceProof
from lonora_core.user_error import LonoraError
from lonora_db.authority_lock import authority_lock
from lonora_db.schema import AccountAuthorityRow
from sqlalchemy import select

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
        from lonora_db.account_authority import changed as authority_changed
        from lonora_db.agent_permissions import bump_permission
        from lonora_db.tasks import stop_management_task

        authorities = list(
            await session.scalars(
                select(AccountAuthorityRow).where(
                    AccountAuthorityRow.owner_id == owner.id,
                    AccountAuthorityRow.device_id == device.id,
                    AccountAuthorityRow.status == "active",
                )
            )
        )
        # Device verification and revocation share the owner-device lock. Lock
        # every affected Agent before mutation too, so a final send is admitted
        # either before revocation or rejected by the newly committed state.
        for agent_id in sorted({row.agent_id for row in authorities}):
            await authority_lock(session, agent_id)
        device.revoked = True
        changed_agents: set[str] = set()
        for authority in authorities:
            await session.refresh(authority)
            if authority.status != "active":
                continue
            authority.status = "revoked"
            await stop_management_task(
                session, authority.owner_id, authority.agent_id, authority.id
            )
            authority_changed(session, authority)
            changed_agents.add(authority.agent_id)
        for agent_id in sorted(changed_agents):
            await bump_permission(session, owner.id, agent_id)
    return {"revoked": True}
