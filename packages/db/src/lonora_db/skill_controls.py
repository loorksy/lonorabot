"""Owner-scoped, bounded Skill version denials independent of installed resources.

Reuse settings and durable events. A Skill deletion/reinstall cannot erase a
version denial; source labels and content hashes cannot circumvent it.
"""

from hashlib import sha256

from lonora_contracts.domain import utcnow
from lonora_contracts.skills import (
    MAX_SKILL_REVOCATIONS,
    SkillRevokeRequest,
    SkillVersionControls,
    SkillVersionRevocation,
)
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import SettingRow
from .transactions import SettingsRepository, owned_agent


def control_key(owner_id: str, agent_id: str) -> str:
    return "skill-versions:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


async def read_skill_controls(
    session: AsyncSession, owner_id: str, agent_id: str
) -> SkillVersionControls:
    await owned_agent(session, owner_id, agent_id)
    payload = await SettingsRepository().get(session, control_key(owner_id, agent_id))
    try:
        controls = (
            SkillVersionControls.model_validate(payload)
            if payload
            else SkillVersionControls(owner_id=owner_id, agent_id=agent_id)
        )
    except ValidationError:
        raise LonoraError("skill_controls_invalid", 409) from None
    if controls.owner_id != owner_id or controls.agent_id != agent_id:
        raise LonoraError("skill_control_scope_mismatch", 409)
    return controls


async def revoke_skill_version(
    session: AsyncSession, owner_id: str, agent_id: str, request: SkillRevokeRequest
) -> SkillVersionControls:
    # Agent lock serializes first insert and future updates, including concurrent
    # calls when no settings row exists yet. No provider/network call runs here.
    await owned_agent(session, owner_id, agent_id, lock=True)
    controls = await read_skill_controls(session, owner_id, agent_id)
    if any(
        item.skill_id == request.skill_id and item.version == request.version
        for item in controls.revoked
    ):
        return controls  # Immutable, idempotent denial; do not rewrite reason/time.
    if request.expected_revision != controls.revision:
        raise LonoraError("version_conflict", 409)
    if len(controls.revoked) >= MAX_SKILL_REVOCATIONS:
        raise LonoraError("skill_revocation_limit", 409)
    revocation = SkillVersionRevocation(
        skill_id=request.skill_id,
        version=request.version,
        reason=request.reason,
        revoked_at=utcnow(),
    )
    updated = controls.model_copy(
        update={"revision": controls.revision + 1, "revoked": [*controls.revoked, revocation]}
    )
    await SettingsRepository().put(
        session, control_key(owner_id, agent_id), updated.model_dump(mode="json")
    )
    emit(
        session,
        owner_id,
        "skill.version_revoked",
        agent_id=agent_id,
        payload={**revocation.model_dump(mode="json"), "revision": updated.revision},
    )
    return updated


async def delete_skill_controls(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """Remove scoped configuration when the Agent itself is permanently deleted."""
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(SettingRow, control_key(owner_id, agent_id))
    if row is not None:
        await session.delete(row)
