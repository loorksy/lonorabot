"""Device-verified activation of immutable, bounded account delegation."""

import json
from typing import Any

from lonora_contracts.account_authority import AccountAuthorityEnvelope
from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import DeviceProof
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import changed, owned_authority, validate_scope
from lonora_db.schema import AccountAuthorityRow
from lonora_db.super_bot import authority_lock
from lonora_session.idempotency import request_hash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import generate_authentication_options, options_to_json
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from .devices import (
    devices,
    new_challenge,
    pending_challenge,
    relying_party,
    verified_device_assertion,
)
from .identity import OwnerIdentity


async def begin_activation(
    session: AsyncSession, owner: OwnerIdentity, identifier: str, origin: str
) -> dict[str, Any]:
    rp = relying_party(origin)
    await authority_lock(session, owner.id + ":devices")
    row = await owned_authority(session, owner.id, identifier)
    if (
        row.status != "pending"
        or row.activation_expires_at <= utcnow()
        or row.valid_until <= utcnow()
    ):
        raise LonoraError("account_authority_expired_or_used", 409)
    known = await devices(session, owner.id)
    if not known:
        raise LonoraError("device_registration_required", 409)
    challenge = await new_challenge(
        session, owner, "account_activate", row.envelope_hash, request_id=row.id
    )
    options = generate_authentication_options(
        rp_id=rp,
        challenge=base64url_to_bytes(challenge.challenge),
        timeout=120000,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in known
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {"challenge_id": challenge.id, "publicKey": json.loads(options_to_json(options))}


async def finish_activation(
    session: AsyncSession,
    owner: OwnerIdentity,
    body: DeviceProof,
    origin: str,
    native_origins: list[str] | None = None,
) -> AccountAuthorityRow:
    challenge = await pending_challenge(
        session, owner, body.challenge_id, "account_activate", allow_used=True
    )
    if challenge.status == "used":
        return await owned_authority(session, owner.id, challenge.request_id or "")
    candidate = await owned_authority(session, owner.id, challenge.request_id or "")
    await authority_lock(session, candidate.agent_id)
    row = await owned_authority(session, owner.id, candidate.id, lock=True)
    if (
        row.status != "pending"
        or row.activation_expires_at <= utcnow()
        or row.valid_until <= utcnow()
        or challenge.binding_hash != row.envelope_hash
        or request_hash(row.envelope) != row.envelope_hash
    ):
        raise LonoraError("account_authority_expired_or_changed", 409)
    envelope = AccountAuthorityEnvelope.model_validate(row.envelope)
    if (
        envelope.valid_until != row.valid_until
        or envelope.account_id != row.account_id
        or envelope.thread_id != row.thread_id
    ):
        raise LonoraError("account_authority_changed", 403)
    await validate_scope(session, owner.id, row.agent_id, envelope)
    device, sign_count = await verified_device_assertion(
        session, owner.id, body, challenge, origin, native_origins
    )
    previous = await session.scalars(
        select(AccountAuthorityRow).where(
            AccountAuthorityRow.owner_id == owner.id,
            AccountAuthorityRow.agent_id == row.agent_id,
            AccountAuthorityRow.account_id == row.account_id,
            AccountAuthorityRow.status == "active",
        )
    )
    for prior in previous:
        prior.status = "revoked"
        changed(session, prior)
    await session.flush()
    device.sign_count, challenge.status = sign_count, "used"
    row.status, row.device_id = "active", device.id
    changed(session, row)
    return row
