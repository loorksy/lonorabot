"""Durable memory: the shared owner profile and this Agent's own document.

USER.md is the one owner profile every Agent reads. Lonora writes what it learns of
the owner, from his words or his behavior (8.2), the latter only in a run it or the
owner started that read nothing others wrote; a team agent writes it only from what
the owner said in the conversation the Run answers. Each write records the Agent and the owner's message, if
any, so the owner sees what he said and what was observed, and can revert it. The
structured reach-me record changes only on the owner's typed message. MEMORY.md
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
from lonora_db.schema import AgentRow, EffectReceiptRow
from lonora_memory.commit import atomic_commit, atomic_edit
from lonora_memory.edits import MemoryEdit, MemoryEditError, MemoryOverflow
from lonora_memory.method import method_history, restore_method
from lonora_memory.profile import LEGACY_USER_VIEW, agent_memory_view, profile_documents
from pydantic import Field, model_validator

from .base import Tool, eager_for
from .context import ToolContext
from .profile_taint import run_read_others, woken_by_marked_row
from .restrictions import OWNER_TRIGGERS, owner_message_id


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
    # Lonora's USER.md lines inferred from the owner's behavior, not his words (8.2, 8.4).
    observed: bool = False

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
    "recovery": "Nothing was saved. A team agent records in the owner profile only what the "
    "owner said in the conversation this run answers; keep other observations in MEMORY.md. "
    "Only the owner's words or Lonora's own observations enter the profile.",
}

# Runs Lonora starts itself or the owner starts: what it observes there is its own (8.2).
# A peer, subagent, follow-up, task, webhook or other wake carries someone else's words.
OBSERVATION_TRIGGERS = OWNER_TRIGGERS | {"routine", "watch", "broker_event", "owner_card"}

OWNER_PROFILE_TAINTED = {
    "ok": False,
    "code": "owner_profile_tainted_run",
    "recovery": "Nothing was saved. This run was started by someone other than you or the "
    "owner, or read content others wrote, so what it saw may be steered. Note it in "
    "MEMORY.md and confirm it in a routine run or with the owner.",
}

PREFERENCES_MESSAGE_REQUIRED = {
    "ok": False,
    "code": "owner_preferences_require_owner_message",
    "recovery": "Nothing was changed. Reach-me, reply language, quiet hours and time zone "
    "change only on the owner's typed message; a pattern you observed belongs in USER.md.",
}


async def _owner_message(context: ToolContext) -> tuple[str | None, bool, bool]:
    """The owner's typed message this run answers, whether the caller is Lonora, and
    whether the run is tainted for an observation without that message (6.10): another
    agent, a script or a webhook started it, or it read content others wrote."""
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        message_id = await owner_message_id(session, run)
        agent = await session.get(AgentRow, context.agent_id)
        lead = bool(agent and agent.role == "personal")
        tainted = False
        if lead and message_id is None:
            # A routine, watch or opportunity a run that read others' content made wakes
            # without observations too; that mark is read here only (profile_taint.py).
            tainted = (
                run.trigger not in OBSERVATION_TRIGGERS
                or await run_read_others(session, run)
                or await woken_by_marked_row(session, run)
            )
        return message_id, lead, tainted


async def write(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = MemoryWrite.model_validate(args)
    message_id, lead, tainted = await _owner_message(context)
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
        profile = any(edit.section == "USER.md" for edit in edits)
        # Lonora writes its observations of the owner without his message (8.2); a team
        # agent records only the owner's words.
        if profile and not lead and (message_id is None or params.observed):
            return OWNER_MESSAGE_REQUIRED
        if profile and tainted:
            return OWNER_PROFILE_TAINTED
        if params.observed:
            # An observation is never attributed to the owner's message.
            message_id = None
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


class MethodHistoryInput(Contract):
    version: int | None = Field(default=None, ge=1)


class MethodRestoreInput(Contract):
    version: int = Field(ge=1)
    memory_version: int = Field(ge=1)


async def method_versions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = MethodHistoryInput.model_validate(args)
    async with context.db.sessions() as session:
        return await method_history(
            session, context.owner_id, context.agent_id, version=params.version
        )


async def method_restore(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = MethodRestoreInput.model_validate(args)
    return await restore_method(
        context.db,
        context.owner_id,
        context.agent_id,
        params.version,
        params.memory_version,
        lease=context.lease,
        effect_key=context.effect_key,
        source_message_id=(await _owner_message(context))[0],
    )


class OwnerPreferencesUpdate(Contract):
    reach_me: ReachMe | None = None
    reply_language: Literal["ar", "en", "auto"] | None = None
    # Quiet hours to the minute (Q47), local "HH:MM" in the owner's time zone.
    quiet_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    clear_quiet_hours: bool = False
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def something_to_change(self) -> Self:
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("incoming_call_quiet_hours_incomplete")
        if self.quiet_start is not None and self.quiet_start == self.quiet_end:
            raise ValueError("incoming_call_quiet_hours_empty")
        if self.clear_quiet_hours and self.quiet_start is not None:
            raise ValueError("quiet_hours_conflict")
        if (
            self.reach_me is None
            and self.reply_language is None
            and self.quiet_start is None
            and self.timezone is None
            and not self.clear_quiet_hours
        ):
            raise ValueError("owner_preferences_empty")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ValueError, ZoneInfoNotFoundError, OSError) as error:
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
            return PREFERENCES_MESSAGE_REQUIRED
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
        elif params.quiet_start is not None and params.quiet_end is not None:
            for side, value in (("start", params.quiet_start), ("end", params.quiet_end)):
                hour, minute = (int(part) for part in value.split(":"))
                changes[f"quiet_{side}_hour"] = hour
                changes[f"quiet_{side}_minute"] = hour * 60 + minute
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
            "appends content to USER.md (shared owner profile: his words; Lonora's inferences "
            "with observed), MEMORY.md (your knowledge) or OPERATING.md (your method); "
            "patch replaces unique old_text with content; remove deletes the lines old_text "
            "touches. A duplicate add returns changed false; overflow returns the shortfall. "
            "content replaces your document at version. No credentials or current prices. "
            "Say remembered only after success.",
            MemoryWrite,
            write,
            replay_safe=True,
            eager=eager_for("core"),
        ),
        Tool(
            "method_history",
            "List the versions of your method (your OPERATING.md): every write is a version "
            "with its number, author and an excerpt. With version, read that version in full.",
            MethodHistoryInput,
            method_versions,
            True,
            search_terms="method versions history revisions strategy rollback "
            "إصدارات المنهج سجل الطريقة الاستراتيجية",
        ),
        Tool(
            "method_restore",
            "Restore your method (OPERATING.md) to a version from method_history, when you or "
            "the owner decide an earlier version was better; memory_version is the one "
            "method_history returned. It saves a new version with that text; MEMORY.md stays.",
            MethodRestoreInput,
            method_restore,
            replay_safe=True,
            search_terms="revert method restore version undo strategy "
            "استرجاع المنهج الرجوع إلى إصدار تراجع",
        ),
        Tool(
            "owner_preferences_update",
            "Set the owner's shared preferences from what he typed: reach_me (activity, notify, "
            "message or call: how to reach him when something needs him), reply_language (ar, "
            "en, or auto: his latest message's language), quiet hours as local HH:MM "
            "(quiet_start, quiet_end), timezone. Every Agent "
            "follows them from its next run; the owner can revert. Delivery is in-app only.",
            OwnerPreferencesUpdate,
            update_preferences,
            replay_safe=True,
        ),
    ]
