"""Standard WebAuthn user verification; no biometric booleans or device secrets."""

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import DeviceEnrollment, DeviceProof, SuperBotEnvelope
from lonora_core.user_error import LonoraError
from lonora_db.schema import DeviceChallengeRow, DeviceCredentialRow, OwnerRow, SuperBotRequestRow
from lonora_db.super_bot import authority_lock, changed, owned_request, plan_hash, stop_request
from lonora_session.idempotency import request_hash
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .account_security import verify_password
from .identity import OwnerIdentity


def relying_party(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or (
            parsed.scheme != "https"
            and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
        )
    ):
        raise LonoraError("device_secure_origin_required", 409)
    return parsed.hostname


async def devices(session: AsyncSession, owner_id: str) -> list[DeviceCredentialRow]:
    return list(
        await session.scalars(
            select(DeviceCredentialRow).where(
                DeviceCredentialRow.owner_id == owner_id, DeviceCredentialRow.revoked.is_(False)
            )
        )
    )


async def new_challenge(
    session: AsyncSession,
    owner: OwnerIdentity,
    kind: str,
    binding: str,
    *,
    request_id: str | None = None,
    name: str = "",
) -> DeviceChallengeRow:
    await authority_lock(session, owner.id + ":devices")
    await session.execute(
        delete(DeviceChallengeRow).where(
            DeviceChallengeRow.owner_id == owner.id,
            DeviceChallengeRow.expires_at < utcnow() - timedelta(days=1),
        )
    )
    count = await session.scalar(
        select(func.count())
        .select_from(DeviceChallengeRow)
        .where(
            DeviceChallengeRow.owner_id == owner.id,
            DeviceChallengeRow.status == "pending",
            DeviceChallengeRow.expires_at > utcnow(),
        )
    )
    if (count or 0) >= 8:
        raise LonoraError("device_challenge_limit", 429)
    row = DeviceChallengeRow(
        owner_id=owner.id,
        session_hash=owner.token_hash,
        kind=kind,
        request_id=request_id,
        challenge=bytes_to_base64url(secrets.token_bytes(32) + bytes.fromhex(binding)),
        binding_hash=binding,
        name=name,
        expires_at=utcnow() + timedelta(seconds=120),
    )
    session.add(row)
    await session.flush()
    return row


async def pending_challenge(
    session: AsyncSession,
    owner: OwnerIdentity,
    identifier: str,
    kind: str,
    *,
    allow_used: bool = False,
) -> DeviceChallengeRow:
    await authority_lock(session, owner.id + ":devices")
    row = await session.get(
        DeviceChallengeRow, identifier, with_for_update=True, populate_existing=True
    )
    if (
        row is None
        or row.owner_id != owner.id
        or row.session_hash != owner.token_hash
        or row.kind != kind
    ):
        raise LonoraError("device_challenge_not_found", 404)
    if row.status == "used" and allow_used:
        return row
    if row.status != "pending" or row.expires_at <= utcnow():
        raise LonoraError("device_challenge_expired_or_used", 409)
    return row


def credential_size(proof: DeviceProof) -> None:
    if len(json.dumps(proof.credential)) > 65536:
        raise LonoraError("device_proof_invalid", 422)


async def begin_enrollment(
    session: AsyncSession, owner: OwnerIdentity, body: DeviceEnrollment, origin: str
) -> dict[str, Any]:
    rp = relying_party(origin)
    await authority_lock(session, owner.id + ":devices")
    account = await session.get(OwnerRow, owner.id)
    if account is None or not verify_password(
        body.password.get_secret_value(), account.password_hash
    ):
        raise LonoraError("unauthorized", 401)
    known = await devices(session, owner.id)
    if len(known) >= 16:
        raise LonoraError("device_limit", 409)
    challenge = await new_challenge(
        session,
        owner,
        "register",
        hashlib.sha256((owner.id + ":" + rp).encode()).hexdigest(),
        name=body.name,
    )
    options = generate_registration_options(
        rp_id=rp,
        rp_name="Lonora",
        user_id=owner.id.encode(),
        user_name=owner.email,
        challenge=base64url_to_bytes(challenge.challenge),
        timeout=120000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in known
        ],
        supported_pub_key_algs=[COSEAlgorithmIdentifier.ECDSA_SHA_256],
    )
    return {"challenge_id": challenge.id, "publicKey": json.loads(options_to_json(options))}


async def finish_enrollment(
    session: AsyncSession,
    owner: OwnerIdentity,
    body: DeviceProof,
    origin: str,
    native_origins: list[str] | None = None,
) -> dict[str, Any]:
    credential_size(body)
    row = await pending_challenge(session, owner, body.challenge_id, "register")
    try:
        result = verify_registration_response(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(row.challenge),
            expected_rp_id=relying_party(origin),
            expected_origin=[origin] + (native_origins or []),
            require_user_presence=True,
            require_user_verification=True,
            supported_pub_key_algs=[COSEAlgorithmIdentifier.ECDSA_SHA_256],
        )
    except Exception as error:
        raise LonoraError("device_proof_invalid", 403) from error
    existing = await session.scalar(
        select(DeviceCredentialRow).where(
            DeviceCredentialRow.credential_id == bytes_to_base64url(result.credential_id)
        )
    )
    if existing or len(await devices(session, owner.id)) >= 16:
        raise LonoraError("device_already_registered_or_limit", 409)
    row.status = "used"
    device = DeviceCredentialRow(
        owner_id=owner.id,
        name=row.name,
        credential_id=bytes_to_base64url(result.credential_id),
        public_key=bytes_to_base64url(result.credential_public_key),
        sign_count=result.sign_count,
    )
    session.add(device)
    await session.flush()
    return {"id": device.id, "name": device.name}


async def begin_activation(
    session: AsyncSession, owner: OwnerIdentity, request_id: str, origin: str
) -> dict[str, Any]:
    rp = relying_party(origin)
    await authority_lock(session, owner.id + ":devices")
    row = await owned_request(session, owner.id, request_id)
    if row.status != "pending" or row.expires_at <= utcnow():
        raise LonoraError("super_bot_request_expired_or_used", 409)
    known = await devices(session, owner.id)
    if not known:
        raise LonoraError("device_registration_required", 409)
    challenge = await new_challenge(
        session, owner, "activate", row.envelope_hash, request_id=row.id
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
) -> SuperBotRequestRow:
    from lonora_db.agent_binding import require_financial_agent
    from lonora_db.trading_goals import owned_goal, require_autonomous_limits, update_goal_state

    credential_size(body)
    challenge = await pending_challenge(
        session, owner, body.challenge_id, "activate", allow_used=True
    )
    if challenge.status == "used":
        # A lost HTTP response may reread the existing result; it never applies
        # authority again, including after pause, revocation or replacement.
        return await owned_request(session, owner.id, challenge.request_id or "")
    row = await owned_request(session, owner.id, challenge.request_id or "")
    await authority_lock(session, row.agent_id)
    goal = await owned_goal(session, owner.id, row.goal_id, True)
    row = await owned_request(session, owner.id, row.id, lock=True)
    if (
        row.status != "pending"
        or row.expires_at <= utcnow()
        or challenge.binding_hash != row.envelope_hash
        or request_hash(row.envelope) != row.envelope_hash
    ):
        raise LonoraError("super_bot_request_expired_or_changed", 409)
    envelope = SuperBotEnvelope.model_validate(row.envelope)
    agent = await require_financial_agent(session, owner.id, row.agent_id)
    if (
        row.mode != envelope.mode
        or goal.state.get("status") in {"cancelled", "completed"}
        or goal.state.get("plan_version", 1) != envelope.plan_version
        or plan_hash(goal) != envelope.plan_hash
        or agent.execution_mode != envelope.execution_mode
        or goal.payload.get("maximum_volume")
        != (str(envelope.maximum_volume) if envelope.maximum_volume is not None else None)
        or goal.payload["max_trade_actions"] != envelope.max_trade_actions
    ):
        raise LonoraError("super_bot_plan_changed", 409)
    device = await session.scalar(
        select(DeviceCredentialRow)
        .where(
            DeviceCredentialRow.owner_id == owner.id,
            DeviceCredentialRow.credential_id == body.credential.get("id"),
            DeviceCredentialRow.revoked.is_(False),
        )
        .with_for_update()
    )
    if device is None:
        raise LonoraError("device_proof_invalid", 403)
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=relying_party(origin),
            expected_origin=[origin] + (native_origins or []),
            credential_public_key=base64url_to_bytes(device.public_key),
            credential_current_sign_count=device.sign_count,
            require_user_verification=True,
        )
    except Exception as error:
        raise LonoraError("device_proof_invalid", 403) from error
    if row.mode == "autonomous":
        require_autonomous_limits(goal)
    previous = list(
        await session.scalars(
            select(SuperBotRequestRow).where(
                SuperBotRequestRow.goal_id == row.goal_id,
                SuperBotRequestRow.status == "activated",
            )
        )
    )
    for prior in previous:
        await stop_request(session, prior, "disabled")
    await session.flush()
    device.sign_count, challenge.status = verified.new_sign_count, "used"
    row.status, row.device_id = "activated", device.id
    update_goal_state(
        session,
        goal,
        {**goal.state, "autonomous": row.mode == "autonomous", "super_bot_request_id": row.id},
    )
    changed(session, row)
    return row
