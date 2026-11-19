"""Register and remove this phone for push (VISION 11.4). Owner session only; the token is
encrypted at rest, bound to the session that sent it, and never returned or logged."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.push import DEVICE_ID, PushDeviceRegistration
from lonora_core.user_error import LonoraError
from lonora_db.push_devices import register_device, remove_device
from lonora_security.secrets import SecretCipher

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/push/devices")
DeviceId = Annotated[str, Path(pattern=DEVICE_ID)]


@router.put("/{device_id}")
async def register(
    request: Request,
    device_id: DeviceId,
    body: PushDeviceRegistration,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, bool]:
    rt = runtime(request)
    cipher = SecretCipher(rt.settings.encryption_key.get_secret_value())
    async with rt.db.sessions() as session, session.begin():
        await register_device(session, owner.id, owner.token_hash, device_id, body, cipher)
    return {"registered": True}


@router.delete("/{device_id}")
async def remove(
    request: Request, device_id: DeviceId, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        if not await remove_device(session, owner.id, device_id):
            raise LonoraError("push_device_not_found", 404)
    return {"removed": True}
