"""Progressive Skill reads owned by the existing Agent context lifecycle.

Views remain conservatively active through the Run. A receipt pins content before
returning it; only a verified result exchange admits those IDs into a checkpoint.
"""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, EffectReceiptRow, RunRow, SkillRow, ThreadRow
from lonora_session.idempotency import request_hash
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..context.skills import effective_skill_registry, pin_package_image
from .registry import SkillRegistry
from .resolver import SkillSelection, SkillSignals, resolve_skills
from .snapshot import MAX_SNAPSHOT_SKILLS, read_snapshot, write_snapshot

VIEW_KIND = "skill-view-v1"
ACTIVE_BUDGET = 16000


def view_key(context: ToolContext) -> str:
    return (
        "skill-view:" + sha256((context.lease.run_id + ":" + context.call_id).encode()).hexdigest()
    )


def view_digest(context: ToolContext, skill_id: str) -> str:
    return request_hash(
        {
            "kind": VIEW_KIND,
            "owner_id": context.owner_id,
            "agent_id": context.agent_id,
            "thread_id": context.thread_id,
            "run_id": context.lease.run_id,
            "call_id": context.call_id,
            "skill_id": skill_id,
        }
    )


async def scoped_run(session: AsyncSession, context: ToolContext) -> RunRow:
    run = await require_lease(session, context.lease, lock=True)
    thread = await session.get(ThreadRow, run.thread_id)
    agent = await session.get(AgentRow, run.agent_id)
    if (
        not context.call_id
        or run.agent_id != context.agent_id
        or run.thread_id != context.thread_id
        or thread is None
        or agent is None
        or thread.owner_id != context.owner_id
        or agent.owner_id != context.owner_id
    ):
        raise LonoraError("skill_scope_mismatch", 409)
    return run


async def catalog_state(
    session: AsyncSession, context: ToolContext, registry: ToolRegistry, run: RunRow
) -> tuple[SkillRegistry, dict[str, str], SkillSignals]:
    rows = (
        await session.scalars(select(SkillRow).where(SkillRow.agent_id == context.agent_id))
    ).all()
    skills, rejected = await effective_skill_registry(
        session, context, registry, rows, run.model_metadata
    )
    read_only = run.trigger == "subagent" or run.model_metadata.get("authority") == "observe_only"
    return (
        skills,
        rejected,
        SkillSignals(
            trigger="",
            read_only=read_only,
            available_tools=frozenset(item.name for item in registry.definitions(read_only)),
        ),
    )


def select_bundle(
    skills: SkillRegistry,
    rejected: dict[str, str],
    signals: SkillSignals,
    active_ids: tuple[str, ...],
    skill_id: str,
) -> tuple[SkillSelection, SkillSelection]:
    from dataclasses import replace

    if len(active_ids) > MAX_SNAPSHOT_SKILLS:
        raise LonoraError("skill_snapshot_invalid", 409)
    requested = frozenset((*active_ids, skill_id))
    combined = resolve_skills(
        skills, replace(signals, requested=requested), ACTIVE_BUDGET, rejected
    )
    selected = {item.manifest.id for item in combined.selected}
    if not requested <= selected:
        # An admission must never silently replace older active instructions.
        failure = next(
            (
                combined.rejected.get(identity, "skill_not_found")
                for identity in [skill_id, *active_ids]
                if identity not in selected
            ),
            "skill_unavailable",
        )
        raise LonoraError(failure, 409)
    bundle = resolve_skills(
        skills, replace(signals, requested=frozenset({skill_id})), ACTIVE_BUDGET, rejected
    )
    if skill_id not in {item.manifest.id for item in bundle.selected}:
        raise LonoraError(bundle.rejected.get(skill_id, "skill_unavailable"), 409)
    return combined, bundle


def admission_snapshot(metadata: dict[str, Any], selection: SkillSelection) -> dict[str, Any]:
    previous = read_snapshot(metadata.get("skill_snapshot"))
    try:
        return write_snapshot(previous, selection)
    except LonoraError as error:
        # The existing snapshot was validated before attempting this addition.
        if error.code == "skill_snapshot_invalid":
            raise LonoraError("skill_snapshot_budget_exceeded", 409) from None
        raise


def acknowledgment(skill_id: str, selection: SkillSelection) -> dict[str, Any]:
    return {
        "skill_id": skill_id,
        "skills": [
            {
                "id": item.manifest.id,
                "version": item.manifest.version,
                "source": item.manifest.source,
                "provenance": "bundled" if item.manifest.source == "builtin" else "owner_supplied",
                "content_sha256": sha256(item.content.encode()).hexdigest(),
                "content": item.content,
            }
            for item in selection.selected
        ],
        "authority_granted": False,
        "instruction_char_budget": ACTIVE_BUDGET,
        "instruction_chars": len(selection.context()),
    }


def verify_receipt(
    context: ToolContext, skill_id: str, receipt: EffectReceiptRow, expected: dict[str, Any]
) -> dict[str, Any]:
    if (
        receipt.result.get("kind") != VIEW_KIND
        or receipt.result.get("digest") != view_digest(context, skill_id)
        or receipt.result.get("acknowledgment") != expected
    ):
        raise LonoraError("skill_view_identity_conflict", 409)
    return expected


@dataclass(frozen=True)
class RunSkillAccess:
    registry: ToolRegistry
    active_ids: tuple[str, ...]

    async def create_package(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from .lifecycle import create_package

        return await create_package(context, self.registry, arguments)

    async def import_package(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from .lifecycle import import_package

        return await import_package(context, self.registry, arguments)

    async def validate_package(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from .lifecycle import validate_package

        return await validate_package(context, arguments)

    async def control_package(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from .lifecycle import control_package

        return await control_package(context, self.registry, arguments)

    async def inspect_repository(
        self, context: ToolContext, repository_url: str, ref: str
    ) -> dict[str, Any]:
        from .repository import inspect_repository

        async with context.db.sessions() as session, session.begin():
            await scoped_run(session, context)
        result = await inspect_repository(repository_url, ref)
        async with context.db.sessions() as session, session.begin():
            await scoped_run(session, context)
        return result

    async def catalog(self, context: ToolContext, offset: int, limit: int) -> dict[str, Any]:
        async with context.db.sessions() as session, session.begin():
            run = await scoped_run(session, context)
            skills, rejected, signals = await catalog_state(session, context, self.registry, run)
            identities = sorted(skills.definitions.keys() | rejected.keys())
            entries: list[dict[str, Any]] = []
            for identity in identities[offset : offset + limit]:
                definition = skills.definitions.get(identity)
                reason: str | None = rejected.get(identity)
                if definition is not None and reason is None:
                    try:
                        combined, _ = select_bundle(
                            skills, rejected, signals, self.active_ids, identity
                        )
                        admission_snapshot(run.model_metadata, combined)
                    except LonoraError as error:
                        reason = error.code
                entries.append(
                    {
                        "id": identity[:100],
                        "version": definition.manifest.version if definition else None,
                        "title": definition.manifest.title if definition else identity[:160],
                        "description": definition.manifest.description[:300] if definition else "",
                        "source": definition.manifest.source if definition else None,
                        "available": reason is None,
                        "code": reason,
                    }
                )
            return {
                "skills": entries,
                "total": len(identities),
                "next_offset": offset + limit if offset + limit < len(identities) else None,
                "read_tool": "skill_view",
                "authority_granted": False,
            }

    async def view(self, context: ToolContext, skill_id: str) -> dict[str, Any]:
        async with context.db.sessions() as session, session.begin():
            run = await scoped_run(session, context)
            receipt = await session.get(EffectReceiptRow, view_key(context))
            if receipt is not None and (
                receipt.result.get("kind") != VIEW_KIND
                or receipt.result.get("digest") != view_digest(context, skill_id)
            ):
                raise LonoraError("skill_view_identity_conflict", 409)
            skills, rejected, signals = await catalog_state(session, context, self.registry, run)
            combined, bundle = select_bundle(skills, rejected, signals, self.active_ids, skill_id)
            expected = acknowledgment(skill_id, bundle)
            rows = (
                await session.scalars(select(SkillRow).where(SkillRow.agent_id == context.agent_id))
            ).all()
            metadata = pin_package_image(run.model_metadata, rows, combined.selected)
            if receipt is not None:
                run.model_metadata = metadata
                return verify_receipt(context, skill_id, receipt, expected)
            run.model_metadata = {
                **metadata,
                "skill_snapshot": admission_snapshot(run.model_metadata, combined),
            }
            session.add(
                EffectReceiptRow(
                    key=view_key(context),
                    result={
                        "kind": VIEW_KIND,
                        "digest": view_digest(context, skill_id),
                        "acknowledgment": expected,
                    },
                )
            )
            return expected


async def admitted_view_ids(
    context: ToolContext,
    registry: ToolRegistry,
    call: ToolCall,
    result: dict[str, Any],
    active_ids: list[str],
) -> list[str]:
    """Bind actual receipt-backed content, never arbitrary result metadata."""
    if call.name != "skill_view" or result.get("ok") is False:
        return []
    # Argument validation already ran in ToolRegistry. Revalidate for receipt recovery.
    from lonora_tools.skills import SkillViewInput

    skill_id = SkillViewInput.model_validate(call.arguments).skill_id
    scoped = context.for_call(call.id)
    async with context.db.sessions() as session, session.begin():
        run = await scoped_run(session, scoped)
        skills, rejected, signals = await catalog_state(session, scoped, registry, run)
        _, bundle = select_bundle(skills, rejected, signals, tuple(active_ids), skill_id)
        expected = acknowledgment(skill_id, bundle)
        receipt = await session.get(EffectReceiptRow, view_key(scoped))
        if receipt is None:
            raise LonoraError("skill_view_receipt_unavailable", 409)
        verify_receipt(scoped, skill_id, receipt, expected)
        if {key: value for key, value in result.items() if key != "ok"} != expected:
            raise LonoraError("skill_view_identity_conflict", 409)
        return [cast(str, item["id"]) for item in expected["skills"]]
