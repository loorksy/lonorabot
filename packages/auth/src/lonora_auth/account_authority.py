"""Device-verified activation of immutable, bounded account delegation."""

import json
from typing import Any

from lonora_bus.attention import attention_text
from lonora_contracts.account_authority import AccountAuthorityEnvelope
from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import DeviceProof
from lonora_contracts.tasks import TaskCreate
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import (
    changed,
    owned_authority,
    require_authority,
    stop_management_task,
    validate_scope,
)
from lonora_db.conversation_locale import conversation_locale
from lonora_db.schema import AccountAuthorityRow, RunRow
from lonora_db.super_bot import authority_lock
from lonora_db.tasks import create_task
from lonora_session.idempotency import request_hash, stable_id
from pydantic import ValidationError
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
        or row.valid_until is not None
        and row.valid_until <= utcnow()
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
    from lonora_db.agent_permissions import bump_permission

    challenge = await pending_challenge(
        session, owner, body.challenge_id, "account_activate", allow_used=True
    )
    candidate = await owned_authority(session, owner.id, challenge.request_id or "")
    await authority_lock(session, candidate.agent_id)
    if challenge.status == "used":
        # An idempotent receipt is valid only while its original signed grant
        # remains effective. Replaying an old proof must never imply activation.
        row, _ = await require_authority(session, owner.id, candidate.agent_id, candidate.id)
        return row
    row = await owned_authority(session, owner.id, candidate.id, lock=True)
    if (
        row.status != "pending"
        or row.activation_expires_at <= utcnow()
        or row.valid_until is not None
        and row.valid_until <= utcnow()
        or challenge.binding_hash != row.envelope_hash
        or request_hash(row.envelope) != row.envelope_hash
    ):
        raise LonoraError("account_authority_expired_or_changed", 409)
    try:
        envelope = AccountAuthorityEnvelope.model_validate(row.envelope)
    except ValidationError as error:
        raise LonoraError("account_authority_changed", 403) from error
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
        await stop_management_task(session, prior)
        changed(session, prior)
    await session.flush()
    device.sign_count, challenge.status = sign_count, "used"
    row.status, row.device_id = "active", device.id
    if envelope.management_mode == "full":
        locale = await conversation_locale(session, owner.id, row.thread_id)
        task = await create_task(
            session,
            owner.id,
            row.agent_id,
            row.thread_id,
            TaskCreate(
                title=attention_text("account_management_task", locale),
                completion_mode="continuous",
                description=(
                    "The owner has authenticated automatic management of account "
                    + row.account_id
                    + ". Inspect the current signed account scope and actual broker state. "
                    "Assess existing positions and relevant markets, choose your own justified "
                    "direction, lot size, stops, targets and management plan within that scope. "
                    "Do not ask for each order or ask the owner to choose routine trading parameters. "
                    "Trade only when fresh evidence supports the action; activation alone is not an entry signal. "
                    "Use the existing journaled trade services and verify actual broker effects. "
                    "Global controls, revocation, exact specialist binding and owner intervention still apply. "
                    "Inspect existing watches and schedules before creating any; persist meaningful "
                    "market-triggered follow-up without duplicate monitoring or continuous model polling. "
                    "Continue useful authorized work while the owner is away. Report actual results "
                    "and concrete blockers concisely in the conversation language; never promise returns. "
                    "A review or reply does not finish this ongoing responsibility. Before yielding, "
                    "persist a real wait on the relevant watch, broker recovery or a justified timer "
                    "so this same work resumes with fresh evidence. Include a brief useful owner update "
                    "with that wait when there is an actual result or changed blocker to report."
                ),
            ),
            task_id=stable_id(row.id, "account-management-task"),
        )
        run = await session.get(RunRow, task.payload["run_id"])
        assert run is not None
        run.model_metadata = {
            **run.model_metadata,
            "account_id": row.account_id,
            "account_management_id": row.id,
            "reply_locale": locale,
        }
    changed(session, row)
    await bump_permission(session, owner.id, row.agent_id)
    return row
