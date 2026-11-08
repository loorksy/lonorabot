"""The one owner profile every Agent reads, with attributed, revertible changes.

The profile has two parts. Its text (USER.md: tone, length, standing rules and
anything else the owner says about himself) is one versioned document. Its
structured preferences are the reply language and the reach-me preference; the
latter is the incoming-call policy record the call gate already enforces, so the
owner never has two settings that disagree. Nothing here grants tools, permissions
or financial authority.
"""

import json
from collections.abc import Callable
from typing import Any, Literal

from lonora_contracts.domain import utcnow
from lonora_contracts.incoming_calls import IncomingCallPolicy, policy_error_code
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .memory import commit_memory, memory_data, memory_view
from .memory_revisions import Author, record_revision, undo_change
from .schema import (
    DeviceCredentialRow,
    EffectReceiptRow,
    MemoryRevisionRow,
    MemoryRow,
    OwnerProfileRow,
    OwnerRow,
)
from .transactions import SettingsRepository

OWNER_PROFILE_CHAR_LIMIT = 8000
REACH_ME_KEY = "incoming-call-policy:"
ReplyLanguage = Literal["ar", "en"]
ProfileTransform = Callable[[str, int], tuple[str, dict[str, Any]]]


def owner_profile_data(row: OwnerProfileRow | None) -> dict[str, Any]:
    return {
        "content": row.content if row else "",
        "version": row.version if row else 1,
        "reply_language": row.reply_language if row else None,
        "updated_at": row.updated_at.isoformat() if row else None,
        "chars": len(row.content) if row else 0,
        "limit": OWNER_PROFILE_CHAR_LIMIT,
    }


async def read_owner_profile(session: AsyncSession, owner_id: str) -> OwnerProfileRow | None:
    return await session.get(OwnerProfileRow, owner_id)


async def locked_owner_profile(session: AsyncSession, owner_id: str) -> OwnerProfileRow:
    """The owner's profile row under a lock, created on first write.

    populate_existing: a row this session read earlier must not hide a commit that
    landed while it waited for the lock, or that commit would be overwritten.
    """
    row = await session.get(OwnerProfileRow, owner_id, with_for_update=True, populate_existing=True)
    if row is not None:
        return row
    # Lock the owner first so two first writes cannot both insert.
    owner = await session.scalar(select(OwnerRow).where(OwnerRow.id == owner_id).with_for_update())
    if owner is None:
        raise LonoraError("owner_not_found", 404)
    row = await session.get(OwnerProfileRow, owner_id, with_for_update=True, populate_existing=True)
    if row is None:
        row = OwnerProfileRow(owner_id=owner_id, content="", version=1, updated_at=utcnow())
        session.add(row)
        await session.flush()
    return row


def profile_summary(row: OwnerProfileRow) -> dict[str, Any]:
    return {
        "document": "owner_profile",
        "version": row.version,
        "updated_at": row.updated_at.isoformat(),
        "chars": len(row.content),
        "limit": OWNER_PROFILE_CHAR_LIMIT,
        "shared_with": "every_agent",
    }


async def commit_owner_profile(
    session: AsyncSession,
    owner_id: str,
    content: str,
    expected_version: int | None,
    *,
    author: Author,
    author_agent_id: str | None = None,
    source_message_id: str | None = None,
    source_run_id: str | None = None,
    effect_key: str | None = None,
    transform: ProfileTransform | None = None,
    change: str | None = None,
    reverted_revision_id: str | None = None,
) -> dict[str, Any]:
    if effect_key:
        receipt = await session.get(EffectReceiptRow, effect_key)
        if receipt:
            return receipt.result
    row = await locked_owner_profile(session, owner_id)
    # None: content-addressed operations or an undo, checked against the locked text.
    if expected_version is not None and row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    details: dict[str, Any] = {}
    if transform is not None:
        content, details = transform(row.content, row.version)
        if content == row.content:
            result = {**profile_summary(row), "changed": False, **details}
            if effect_key:
                session.add(EffectReceiptRow(key=effect_key, result=result))
            return result
    if len(content) > OWNER_PROFILE_CHAR_LIMIT:
        raise LonoraError("owner_profile_too_large", 413)
    previous = row.content
    row.content = content
    row.version += 1
    row.updated_at = utcnow()
    kind = change or ("operations" if transform is not None else "document")
    await record_revision(
        session,
        owner_id,
        document="owner_profile",
        agent_id=None,
        version=row.version,
        previous_content=previous,
        content=content,
        author=author,
        change=kind,
        author_agent_id=author_agent_id,
        source_message_id=source_message_id,
        source_run_id=source_run_id,
        reverted_revision_id=reverted_revision_id,
    )
    result = (
        owner_profile_data(row)
        if transform is None
        else {**profile_summary(row), "changed": True, **details}
    )
    if effect_key:
        session.add(EffectReceiptRow(key=effect_key, result=result))
    emit(
        session,
        owner_id,
        "owner_profile.updated",
        agent_id=author_agent_id,
        run_id=source_run_id,
        payload={"version": row.version, "author": author, "change": kind},
    )
    return result


# --- Structured preferences: reply language and reach-me ------------------------------


async def reach_me_lock(session: AsyncSession, owner_id: str) -> None:
    """The same owner lock incoming invitations take, so a change and a call serialize."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "incoming-call:" + owner_id},
        )


async def reach_me_policy(
    session: AsyncSession, owner_id: str, *, fresh: bool = False
) -> IncomingCallPolicy:
    """The stored preference; ``fresh`` after reach_me_lock reads the current one even if
    this session loaded the row before the lock."""
    return IncomingCallPolicy.model_validate(
        await SettingsRepository().get(session, REACH_ME_KEY + owner_id, fresh=fresh)
    )


async def verified_device(session: AsyncSession, owner_id: str, device_id: str) -> None:
    device = await session.get(DeviceCredentialRow, device_id)
    if device is None or device.owner_id != owner_id or device.revoked:
        raise LonoraError("incoming_call_device_unavailable", 403)


async def enrolled_devices(session: AsyncSession, owner_id: str) -> list[DeviceCredentialRow]:
    return list(
        await session.scalars(
            select(DeviceCredentialRow)
            .where(DeviceCredentialRow.owner_id == owner_id, DeviceCredentialRow.revoked.is_(False))
            .order_by(DeviceCredentialRow.created_at.desc())
        )
    )


def preferences_snapshot(policy: IncomingCallPolicy, reply_language: str | None) -> str:
    """Canonical text of the structured preferences, as a revision stores it."""
    return json.dumps(
        {"reply_language": reply_language, "reach_me": policy.model_dump(mode="json")},
        sort_keys=True,
        ensure_ascii=False,
    )


def _quiet(policy: dict[str, Any]) -> str | None:
    start, end = policy.get("quiet_start_hour"), policy.get("quiet_end_hour")
    return None if start is None or end is None else f"{start}-{end}"


PREFERENCE_FIELDS: tuple[tuple[str, Callable[[dict[str, Any]], Any]], ...] = (
    ("reply_language", lambda value: value.get("reply_language")),
    ("reach_me", lambda value: value.get("reach_me", {}).get("channel")),
    ("quiet_hours", lambda value: _quiet(value.get("reach_me", {}))),
    ("timezone", lambda value: value.get("reach_me", {}).get("timezone")),
    ("opportunity_calls", lambda value: value.get("reach_me", {}).get("opportunities")),
    ("action_required_calls", lambda value: value.get("reach_me", {}).get("action_required")),
)


def preference_changes(before: str, after: str) -> list[dict[str, Any]]:
    """Field-level changes in plain values; device identifiers are never shown."""
    try:
        old: dict[str, Any] = json.loads(before) if before else {}
        new: dict[str, Any] = json.loads(after) if after else {}
    except ValueError:
        return []
    return [
        {"field": name, "before": read(old), "after": read(new)}
        for name, read in PREFERENCE_FIELDS
        if read(old) != read(new)
    ]


async def save_owner_preferences(
    session: AsyncSession,
    owner_id: str,
    *,
    policy: IncomingCallPolicy | None = None,
    reply_language: ReplyLanguage | None | Literal["keep"] = "keep",
    author: Author,
    author_agent_id: str | None = None,
    source_message_id: str | None = None,
    source_run_id: str | None = None,
    reverted_revision_id: str | None = None,
) -> dict[str, Any]:
    """Save the reach-me preference and/or reply language as one attributed change."""
    await reach_me_lock(session, owner_id)
    current = await reach_me_policy(session, owner_id, fresh=True)
    row = await locked_owner_profile(session, owner_id)
    before = preferences_snapshot(current, row.reply_language)
    target = policy or current
    if policy is not None and policy.enabled:
        # Only a changed reach-me needs a valid device; a language change never fails on it.
        await verified_device(session, owner_id, policy.device_id or "")
    language = row.reply_language if reply_language == "keep" else reply_language
    after = preferences_snapshot(target, language)
    if after == before:
        return {**preferences_data(target, language), "changed": False}
    if policy is not None:
        await SettingsRepository().put(
            session, REACH_ME_KEY + owner_id, policy.model_dump(mode="json")
        )
    row.reply_language = language
    row.updated_at = utcnow()
    revision = await record_revision(
        session,
        owner_id,
        document="owner_preferences",
        agent_id=None,
        version=None,
        previous_content=before,
        content=after,
        author=author,
        change="revert" if reverted_revision_id else "preferences",
        author_agent_id=author_agent_id,
        source_message_id=source_message_id,
        source_run_id=source_run_id,
        reverted_revision_id=reverted_revision_id,
    )
    emit(
        session,
        owner_id,
        "owner_profile.updated",
        agent_id=author_agent_id,
        run_id=source_run_id,
        payload={
            "author": author,
            "change": revision.change,
            "fields": [item["field"] for item in preference_changes(before, after)],
        },
    )
    return {**preferences_data(target, language), "changed": True}


def preferences_data(policy: IncomingCallPolicy, reply_language: str | None) -> dict[str, Any]:
    return {
        "reply_language": reply_language,
        "reach_me": policy.channel,
        "quiet_start_hour": policy.quiet_start_hour,
        "quiet_end_hour": policy.quiet_end_hour,
        "timezone": policy.timezone,
        "device_selected": policy.device_id is not None,
        "opportunity_calls": policy.opportunities,
        "action_required_calls": policy.action_required,
        # In-app only until off-app delivery exists; a call needs Lonora to be open.
        "delivery": "in_app_only",
    }


async def owner_preferences(session: AsyncSession, owner_id: str) -> dict[str, Any]:
    row = await read_owner_profile(session, owner_id)
    return preferences_data(
        await reach_me_policy(session, owner_id), row.reply_language if row else None
    )


# --- Undo -----------------------------------------------------------------------------


def _undo_text(before: str, after: str) -> ProfileTransform:
    def undo(current: str, _version: int) -> tuple[str, dict[str, Any]]:
        content = undo_change(before, after, current)
        if content is None:
            raise LonoraError("memory_revert_conflict", 409)
        return content, {}

    return undo


def undone_preferences(
    revision: MemoryRevisionRow, current: IncomingCallPolicy
) -> tuple[IncomingCallPolicy | None, ReplyLanguage | None | Literal["keep"]]:
    """Only the settings that one change touched, set back onto the current ones."""
    try:
        old: dict[str, Any] = json.loads(revision.previous_content)
        new: dict[str, Any] = json.loads(revision.content)
    except ValueError:
        raise LonoraError("memory_revision_invalid", 409) from None
    old_policy: dict[str, Any] = old.get("reach_me") or {}
    new_policy: dict[str, Any] = new.get("reach_me") or {}
    # enabled follows the channel; it is derived again from the restored channel.
    changed = {
        key: value
        for key, value in old_policy.items()
        if key != "enabled"
        and key in IncomingCallPolicy.model_fields
        and value != new_policy.get(key)
    }
    policy = None
    if changed:
        try:
            policy = IncomingCallPolicy.model_validate(
                {**current.model_dump(mode="json", exclude={"enabled"}), **changed}
            )
        except ValidationError as error:
            raise LonoraError(policy_error_code(error.errors()), 409) from None
    previous_language = old.get("reply_language")
    restored_language: ReplyLanguage | None | Literal["keep"] = "keep"
    if previous_language != new.get("reply_language"):
        restored_language = previous_language if previous_language in ("ar", "en") else None
    return policy, restored_language


async def revert_revision(
    session: AsyncSession,
    owner_id: str,
    revision_id: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Undo one change as a new owner commit; later changes stay as they are.

    Text: the lines that change added go and the lines it removed come back
    (``undo_change``); if a later change edited the same lines nothing is saved and
    the result is ``memory_revert_conflict``. Preferences: only the settings that
    change touched go back. Everything is read under the document's lock first.
    """
    revision = await session.get(MemoryRevisionRow, revision_id)
    if revision is None or revision.owner_id != owner_id:
        raise LonoraError("memory_revision_not_found", 404)
    if revision.document == "agent_memory":
        agent_id = revision.agent_id or ""
        result = await commit_memory(
            session,
            owner_id,
            agent_id,
            "",
            expected_version,
            transform=_undo_text(
                memory_view(revision.previous_content), memory_view(revision.content)
            ),
            change="revert",
            reverted_revision_id=revision.id,
        )
        memory = await session.get(MemoryRow, agent_id)
        if memory is None:
            raise LonoraError("memory_not_found", 404)
        return {**memory_data(memory), "changed": result["changed"]}
    if revision.document == "owner_profile":
        result = await commit_owner_profile(
            session,
            owner_id,
            "",
            expected_version,
            author="owner",
            transform=_undo_text(revision.previous_content, revision.content),
            change="revert",
            reverted_revision_id=revision.id,
        )
        profile = await read_owner_profile(session, owner_id)
        return {**owner_profile_data(profile), "changed": result["changed"]}
    # The lock save_owner_preferences takes, first, so the current settings are final.
    await reach_me_lock(session, owner_id)
    current = await reach_me_policy(session, owner_id, fresh=True)
    policy, language = undone_preferences(revision, current)
    return await save_owner_preferences(
        session,
        owner_id,
        policy=policy,
        reply_language=language,
        author="owner",
        reverted_revision_id=revision.id,
    )
