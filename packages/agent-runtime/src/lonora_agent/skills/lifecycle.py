"""Owned package versions on existing Skill resources and analytical workspace."""

import hashlib
import shlex
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.schema import AnalyticalWorkspaceRow, EffectReceiptRow, SkillRow
from lonora_db.skill_controls import read_skill_controls
from lonora_db.skills import SkillRepository
from lonora_session.idempotency import request_hash
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..workspace import read_snapshot
from ..workspace_access import scoped_run
from .packages import (
    AdaptationReview,
    PackageState,
    PackageVersion,
    fetch_package,
    prepare_package,
    read_state,
)
from .registry import installed_registry


def receipt_key(context: ToolContext) -> str:
    return "skill-package:" + hashlib.sha256(context.effect_key.encode()).hexdigest()


async def prior(session: AsyncSession, context: ToolContext, digest: str) -> dict[str, Any] | None:
    await scoped_run(session, context, mutate=True)
    row = await session.get(EffectReceiptRow, receipt_key(context))
    if row is None:
        return None
    if row.result.get("digest") != digest:
        raise LonoraError("skill_package_identity_conflict", 409)
    return row.result["result"]


def save_receipt(
    session: AsyncSession, context: ToolContext, digest: str, result: dict[str, Any]
) -> None:
    session.add(
        EffectReceiptRow(key=receipt_key(context), result={"digest": digest, "result": result})
    )


async def owned_skill(
    session: AsyncSession, context: ToolContext, identity: str
) -> SkillRow | None:
    return await session.scalar(
        select(SkillRow)
        .where(
            SkillRow.owner_id == context.owner_id,
            SkillRow.agent_id == context.agent_id,
            SkillRow.payload["name"].as_string() == identity,
        )
        .with_for_update()
    )


def current_version(row: SkillRow, expected: int) -> tuple[PackageState, PackageVersion]:
    if row.version != expected:
        raise LonoraError("version_conflict", 409)
    state = read_state(row.state)
    manifest: dict[str, Any] = row.payload.get("manifest") or {}
    entry = next(
        (
            item
            for item in state.versions
            if item.payload.manifest and item.payload.manifest.version == manifest.get("version")
        ),
        None,
    )
    if entry is None or {**row.payload, "enabled": False} != entry.payload.model_dump(mode="json"):
        raise LonoraError("skill_package_content_changed", 409)
    return state, entry


async def assert_unrevoked(
    session: AsyncSession, context: ToolContext, entry: PackageVersion
) -> None:
    controls = await read_skill_controls(session, context.owner_id, context.agent_id)
    assert entry.payload.manifest is not None
    if any(
        item.skill_id == entry.payload.name and item.version == entry.payload.manifest.version
        for item in controls.revoked
    ):
        raise LonoraError("skill_version_revoked", 409)


async def admit_version(
    session: AsyncSession,
    context: ToolContext,
    row: SkillRow | None,
    entry: PackageVersion,
    expected: int,
) -> PackageState | None:
    await assert_unrevoked(session, context, entry)
    controls = await read_skill_controls(session, context.owner_id, context.agent_id)
    denied = {item.version for item in controls.revoked if item.skill_id == entry.payload.name}
    if row is None:
        if expected != 0:
            raise LonoraError("version_conflict", 409)
        # Deletion must not erase a denial or allow relabeling its lost provenance.
        if denied:
            raise LonoraError("skill_version_revoked", 409)
        return None
    state, _ = current_version(row, expected)
    if len(state.versions) >= 8:
        raise LonoraError("skill_package_version_limit", 409)
    assert entry.payload.manifest is not None
    if any(
        item.payload.manifest and item.payload.manifest.version == entry.payload.manifest.version
        for item in state.versions
    ):
        raise LonoraError("skill_package_version_immutable", 409)
    if any(
        item.payload.manifest
        and item.payload.manifest.version in denied
        and (
            item.source_sha256 == entry.source_sha256
            or item.payload.content == entry.payload.content
        )
        for item in state.versions
    ):
        raise LonoraError("skill_version_revoked", 409)
    return state


async def assert_files(
    session: AsyncSession, context: ToolContext, entry: PackageVersion, revision: int
) -> None:
    row = await session.get(AnalyticalWorkspaceRow, context.agent_id)
    if row is None or row.revision != revision or row.active_operation_id:
        raise LonoraError("workspace_revision_conflict", 409)
    files = read_snapshot(row.snapshot)
    if any(
        path not in files or hashlib.sha256(files[path]).hexdigest() != digest
        for path, digest in entry.files.items()
    ):
        raise LonoraError("skill_package_source_changed", 409)


async def validate_graph(
    session: AsyncSession,
    context: ToolContext,
    registry: ToolRegistry,
    payload: dict[str, Any],
    exclude: str | None,
) -> None:
    rows = (
        await session.scalars(select(SkillRow).where(SkillRow.agent_id == context.agent_id))
    ).all()
    _, rejected = installed_registry(
        [row.payload for row in rows if row.id != exclude] + [payload],
        {tool.name for tool in registry.definitions()},
        strict_graph=True,
    )
    name = payload["name"]
    reason = rejected.get(name) or rejected.get(name + "@installed")
    if reason and reason != "skill_disabled":
        raise LonoraError(reason, 409)


def describe(row: SkillRow, entry: PackageVersion, **extra: Any) -> dict[str, Any]:
    assert entry.payload.manifest is not None
    return {
        "skill_id": entry.payload.name,
        "resource_id": row.id,
        "resource_version": row.version,
        "version": entry.payload.manifest.version,
        "enabled": row.payload["enabled"],
        "commit": entry.commit,
        "archive_sha256": entry.archive_sha256,
        "files": entry.files,
        "utilities": entry.utilities,
        "external_imports": entry.external_imports,
        "unmaterialized_dependencies": entry.unmaterialized_dependencies,
        "unsupported_utilities": [path for path in entry.utilities if not path.endswith(".py")],
        "license_files": entry.license_files,
        "adaptation_review": entry.review.model_dump(mode="json"),
        "validation_level": "isolated_smoke_test"
        if entry.validation
        else "instruction_review_only",
        "semantic_equivalence_verified": False,
        "authority_granted": False,
        **extra,
    }


async def import_package(
    context: ToolContext, registry: ToolRegistry, arguments: dict[str, Any]
) -> dict[str, Any]:
    digest = request_hash({"kind": "skill-package-import-v1", **arguments})
    async with context.db.sessions() as session, session.begin():
        if (result := await prior(session, context, digest)) is not None:
            return result
    if context.workspace_access is None:
        raise LonoraError("workspace_runtime_unavailable", 409)
    archive = await fetch_package(arguments["repository_url"], arguments["commit"])
    entry, files = prepare_package(
        archive,
        repository_url=arguments["repository_url"],
        commit=arguments["commit"],
        source_path=arguments["source_path"],
        version=arguments["version"],
        adapted_content=arguments["adapted_content"],
        review=AdaptationReview.model_validate(arguments["review"]),
    )
    identity = entry.payload.name
    # Reserve immutable semantic identities before materializing. No locks span I/O.
    async with context.db.sessions() as session, session.begin():
        await scoped_run(session, context, mutate=True)
        row = await owned_skill(session, context, identity)
        await admit_version(session, context, row, entry, arguments["expected_version"])
        await validate_graph(
            session,
            context,
            registry,
            entry.payload.model_dump(mode="json"),
            row.id if row else None,
        )
    materialized = await context.workspace_access.update(
        context.for_call(context.call_id + ":package-files"),
        arguments["workspace_revision"],
        files,
        [],
    )
    async with context.db.sessions() as session, session.begin():
        if (result := await prior(session, context, digest)) is not None:
            return result
        await assert_files(session, context, entry, materialized["revision"])
        row = await owned_skill(session, context, identity)
        retained = await admit_version(session, context, row, entry, arguments["expected_version"])
        payload = entry.payload.model_dump(mode="json")
        if row:
            assert retained is not None
            state = retained
            state.versions.append(entry)
            row.payload, row.version, row.updated_at = payload, row.version + 1, utcnow()
        else:
            if arguments["expected_version"] != 0:
                raise LonoraError("version_conflict", 409)
            state = PackageState(versions=[entry])
            created = await SkillRepository().create(
                session,
                context.owner_id,
                payload,
                agent_id=context.agent_id,
                resource_id=context.resource_id,
            )
            assert isinstance(created, SkillRow)
            row = created
        await validate_graph(session, context, registry, payload, row.id)
        row.state = {**row.state, "package": state.model_dump(mode="json")}
        result = describe(
            row,
            entry,
            workspace_revision=materialized["revision"],
            status="disabled_pending_validation",
        )
        save_receipt(session, context, digest, result)
        return result


async def validate_package(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    digest = request_hash({"kind": "skill-package-validate-v1", **arguments})
    async with context.db.sessions() as session, session.begin():
        if (result := await prior(session, context, digest)) is not None:
            return result
        row = await owned_skill(session, context, arguments["skill_id"])
        if row is None:
            raise LonoraError("skill_not_found", 404)
        _, entry = current_version(row, arguments["expected_version"])
        await assert_unrevoked(session, context, entry)
        utility = arguments["utility_path"]
        if utility not in entry.utilities or not utility.endswith(".py"):
            raise LonoraError("skill_package_utility_unsupported", 422)
        await assert_files(session, context, entry, arguments["workspace_revision"])
    if context.workspace_access is None:
        raise LonoraError("workspace_runtime_unavailable", 409)
    command = shlex.join(["python3", utility, *arguments["arguments"]])
    outcome = await context.workspace_access.execute(
        context.for_call(context.call_id + ":package-validation"),
        arguments["workspace_revision"],
        command,
        30,
    )
    if "exit_code" not in outcome:
        raise LonoraError("skill_package_validation_interrupted", 409)
    async with context.db.sessions() as session, session.begin():
        if (result := await prior(session, context, digest)) is not None:
            return result
        row = await owned_skill(session, context, arguments["skill_id"])
        if row is None:
            raise LonoraError("skill_not_found", 404)
        state, entry = current_version(row, arguments["expected_version"])
        await assert_unrevoked(session, context, entry)
        await assert_files(session, context, entry, outcome["revision"])
        entry.validation = {
            **(entry.validation or {}),
            utility: {
                "operation_id": outcome["operation_id"],
                "source_sha256": entry.files[utility],
                "image": outcome["image"],
                "exit_code": outcome["exit_code"],
                "arguments": arguments["arguments"],
                "validated_at": utcnow().isoformat(),
            },
        }
        row.state, row.version, row.updated_at = (
            {**row.state, "package": state.model_dump(mode="json")},
            row.version + 1,
            utcnow(),
        )
        result = describe(
            row,
            entry,
            workspace_revision=outcome["revision"],
            exit_code=outcome["exit_code"],
            stdout=outcome["stdout"],
            stderr=outcome["stderr"],
            status="smoke_test_passed" if outcome["exit_code"] == 0 else "smoke_test_failed",
        )
        save_receipt(session, context, digest, result)
        return result


async def control_package(
    context: ToolContext, registry: ToolRegistry, arguments: dict[str, Any]
) -> dict[str, Any]:
    digest = request_hash({"kind": "skill-package-control-v1", **arguments})
    async with context.db.sessions() as session, session.begin():
        if (result := await prior(session, context, digest)) is not None:
            return result
        row = await owned_skill(session, context, arguments["skill_id"])
        if row is None:
            raise LonoraError("skill_not_found", 404)
        state, entry = current_version(row, arguments["expected_version"])
        action = arguments["action"]
        if action == "rollback":
            target = arguments["target_version"]
            entry = next(
                (
                    item
                    for item in state.versions
                    if item.payload.manifest and item.payload.manifest.version == target
                ),
                None,
            )
            if entry is None:
                raise LonoraError("skill_package_version_not_found", 404)
            # Rollback restores disabled instructions, never implicit activation.
            await assert_unrevoked(session, context, entry)
            row.payload = entry.payload.model_dump(mode="json")
        elif action == "activate":
            await assert_unrevoked(session, context, entry)
            await assert_files(session, context, entry, arguments["workspace_revision"])
            if any(
                not (entry.validation or {}).get(path)
                or (entry.validation or {})[path].get("exit_code") != 0
                for path in entry.utilities
            ):
                raise LonoraError("skill_package_validation_required", 409)
            row.payload = {**row.payload, "enabled": True}
        elif action == "disable":
            row.payload = {**row.payload, "enabled": False}
        elif action == "remove":
            # Existing graph constraints remain authoritative on deletion.
            others = (
                await session.scalars(
                    select(SkillRow).where(
                        SkillRow.agent_id == context.agent_id, SkillRow.id != row.id
                    )
                )
            ).all()
            installed_registry(
                [item.payload for item in others],
                {tool.name for tool in registry.definitions()},
                strict_graph=True,
            )
            result = describe(row, entry, status="removed", source_files_retained=True)
            await SkillRepository().delete(session, context.owner_id, row.id)
            save_receipt(session, context, digest, result)
            return result
        else:
            raise LonoraError("skill_package_action_invalid", 422)
        await validate_graph(session, context, registry, row.payload, row.id)
        row.version, row.updated_at = row.version + 1, utcnow()
        result = describe(row, entry, status=action)
        save_receipt(session, context, digest, result)
        return result
