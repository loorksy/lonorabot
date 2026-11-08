"""Durable memory: the shared owner profile and this Agent's own document.

USER.md is the one owner profile every Agent reads. An Agent writes it only from
what the owner said in the conversation the Run answers, and each write records
that Agent and that message so the owner can see and revert it. MEMORY.md
(knowledge) and OPERATING.md (operating notes the Agent refines itself) are the
Agent's private document. Neither grants tools, permissions or financial authority.
"""

from typing import Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lonora_contracts.domain import Contract
from lonora_contracts.incoming_calls import IncomingCallPolicy, ReachMe
from lonora_core.user_error import LonoraError
from lonora_db.memory import memory_data, memory_provenance, read_memory
from lonora_db.owner_profile import (
    enrolled_devices,
    owner_preferences,
    owner_profile_data,
    reach_me_lock,
    reach_me_policy,
    read_owner_profile,
    save_owner_preferences,
)
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow
from lonora_memory.commit import atomic_commit, atomic_edit
from lonora_memory.edits import MemoryEdit, MemoryEditError, MemoryOverflow
from lonora_memory.profile import LEGACY_USER_VIEW, agent_memory_view, profile_documents
from pydantic import Field, model_validator

from .base import Tool, eager_for
from .context import ToolContext
from .restrictions import owner_message_id


class Empty(Contract):
    """No arguments are needed: memory is bound to the current persistent agent."""


class MemoryOperation(Contract):
    action: Literal["add", "patch", "remove"]
    section: Literal["USER.md", "MEMORY.md", "OPERATING.md"] = "MEMORY.md"
    content: str = Field(default="", max_length=8000)
    old_text: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def required_text(self) -> Self:
        if self.action == "add" and not self.content.strip():
            raise ValueError("memory_edit_content_required")
        if self.action != "add" and not self.old_text.strip():
            raise ValueError("memory_edit_old_text_required")
        return self


class MemoryWrite(Contract):
    version: int = Field(ge=1)
    # 0 applies USER.md operations to the current profile; they are content-addressed.
    profile_version: int = Field(default=0, ge=0)
    content: str | None = Field(default=None, max_length=30000)
    operations: list[MemoryOperation] = Field(default_factory=list[MemoryOperation], max_length=20)

    @model_validator(mode="after")
    def one_shape(self) -> Self:
        if (self.content is None) == (not self.operations):
            raise ValueError("memory_write_shape_invalid")
        return self


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await read_memory(session, context.owner_id, context.agent_id)
        shared = owner_profile_data(await read_owner_profile(session, context.owner_id))
        own = memory_data(row)
        view = own["content"]
        return {
            **own,
            "document_sections": [
                name for name in profile_documents(view) if name != LEGACY_USER_VIEW
            ],
            "provenance": await memory_provenance(session, row.agent_id, row.version),
            "owner_profile": {
                "content": shared["content"],
                "profile_version": shared["version"],
                "chars": shared["chars"],
                "limit": shared["limit"],
                "shared_with": "every_agent",
                "preferences": await owner_preferences(session, context.owner_id),
            },
        }


OWNER_MESSAGE_REQUIRED = {
    "ok": False,
    "code": "owner_profile_requires_owner_message",
    "recovery": "Nothing was saved. The shared owner profile records only what the owner "
    "said in the conversation this run answers; keep other observations in MEMORY.md.",
}


async def _owner_message(context: ToolContext) -> str | None:
    async with context.db.sessions() as session:
        return await owner_message_id(session, await require_lease(session, context.lease))


async def write(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = MemoryWrite.model_validate(args)
    message_id = await _owner_message(context)
    try:
        if params.content is not None:
            return await atomic_commit(
                context.db,
                context.owner_id,
                context.agent_id,
                params.content,
                params.version,
                lease=context.lease,
                effect_key=context.effect_key,
                source_message_id=message_id,
            )
        edits = [MemoryEdit(**item.model_dump()) for item in params.operations]
        if message_id is None and any(edit.section == "USER.md" for edit in edits):
            return OWNER_MESSAGE_REQUIRED
        return await atomic_edit(
            context.db,
            context.owner_id,
            context.agent_id,
            edits,
            params.version,
            lease=context.lease,
            effect_key=context.effect_key,
            profile_version=params.profile_version or None,
            source_message_id=message_id,
        )
    except (MemoryEditError, MemoryOverflow) as error:
        # Nothing was saved; the details let the model correct one batch.
        return error.result()
    except LonoraError as error:
        if error.code != "version_conflict":
            raise
        async with context.db.sessions() as session:
            current = await read_memory(session, context.owner_id, context.agent_id)
            profile = owner_profile_data(await read_owner_profile(session, context.owner_id))
        # Operations are content-addressed, so a batch can be re-checked against
        # the newer revision without resending or re-reading the whole document.
        return {
            "ok": False,
            "code": "version_conflict",
            "version": current.version,
            "chars": len(agent_memory_view(current.content)),
            "profile_version": profile["version"],
        }


class OwnerPreferencesUpdate(Contract):
    reach_me: ReachMe | None = None
    reply_language: Literal["ar", "en", "auto"] | None = None
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    clear_quiet_hours: bool = False
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def something_to_change(self) -> Self:
        if (self.quiet_start_hour is None) != (self.quiet_end_hour is None):
            raise ValueError("incoming_call_quiet_hours_incomplete")
        if self.clear_quiet_hours and self.quiet_start_hour is not None:
            raise ValueError("quiet_hours_conflict")
        if (
            self.reach_me is None
            and self.reply_language is None
            and self.quiet_start_hour is None
            and self.timezone is None
            and not self.clear_quiet_hours
        ):
            raise ValueError("owner_preferences_empty")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError) as error:
                raise ValueError("invalid_timezone") from error
        return self


DEVICE_REQUIRED = {
    "ok": False,
    "code": "incoming_call_device_required",
    "recovery": "Nothing was changed. A call needs a device the owner enrolled with a "
    "passkey; ask the owner to enroll one, or reach the owner by message.",
}


async def update_preferences(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = OwnerPreferencesUpdate.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        receipt = await session.get(EffectReceiptRow, context.effect_key)
        if receipt:
            return receipt.result
        message_id = await owner_message_id(session, run)
        if message_id is None:
            return {**OWNER_MESSAGE_REQUIRED, "code": "owner_preferences_require_owner_message"}
        # Lock before reading, so the change applies to the settings as they are now and
        # an owner save or another Agent's change that landed meanwhile is kept.
        await reach_me_lock(session, context.owner_id)
        policy = await reach_me_policy(session, context.owner_id, fresh=True)
        changes: dict[str, Any] = {}
        if params.reach_me is not None:
            changes["channel"] = params.reach_me
            if params.reach_me == "call":
                devices = [
                    device.id for device in await enrolled_devices(session, context.owner_id)
                ]
                if not devices:
                    return DEVICE_REQUIRED
                if policy.device_id not in devices:
                    # The owner's most recently enrolled passkey device rings.
                    changes["device_id"] = devices[0]
                # Being called when his input is needed is what the owner asked for.
                changes["action_required"] = True
        if params.timezone is not None:
            changes["timezone"] = params.timezone
        if params.clear_quiet_hours:
            changes["quiet_start_hour"] = changes["quiet_end_hour"] = None
        elif params.quiet_start_hour is not None:
            changes["quiet_start_hour"] = params.quiet_start_hour
            changes["quiet_end_hour"] = params.quiet_end_hour
        updated = IncomingCallPolicy.model_validate(
            {**policy.model_dump(mode="json", exclude={"enabled"}), **changes}
        )
        language: Literal["ar", "en", "keep"] | None = (
            "keep"
            if params.reply_language is None
            else None
            if params.reply_language == "auto"
            else params.reply_language
        )
        result = {
            **await save_owner_preferences(
                session,
                context.owner_id,
                policy=updated if changes else None,
                reply_language=language,
                author="agent",
                author_agent_id=context.agent_id,
                source_message_id=message_id,
                source_run_id=run.id,
            ),
            "shared_with": "every_agent",
            "revertible": True,
            "execution_authorized": False,
        }
        session.add(EffectReceiptRow(key=context.effect_key, result=result))
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            "memory_read",
            "Read the owner profile all Agents share (USER.md, profile_version, reply and "
            "reach-me preferences) and your own MEMORY.md and OPERATING.md with their revision. "
            "Past conversations: session_search.",
            Empty,
            read,
            True,
            eager=eager_for("core"),
        ),
        Tool(
            "memory_write",
            "Change durable memory atomically. operations apply in order, all or nothing: add "
            "appends content to USER.md (owner profile all Agents share; only what the owner "
            "said), MEMORY.md (your knowledge) or OPERATING.md (your working notes); patch "
            "replaces unique old_text with content; remove deletes the lines old_text touches. "
            "A duplicate add returns changed false; overflow returns the shortfall. content "
            "replaces your document at version. No credentials, prices or authority claims. "
            "Say remembered only after success.",
            MemoryWrite,
            write,
            replay_safe=True,
            eager=eager_for("core"),
        ),
        Tool(
            "owner_preferences_update",
            "Set the owner's shared preferences from what he said: reach_me (activity, notify, "
            "message or call: how to reach him when something needs him), reply_language (ar, "
            "en, or auto: his latest message's language), quiet hours, timezone. Every Agent "
            "follows them from its next run; the owner can revert. Delivery is in-app only.",
            OwnerPreferencesUpdate,
            update_preferences,
            replay_safe=True,
        ),
    ]
