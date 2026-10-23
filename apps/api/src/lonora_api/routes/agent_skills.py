"""Validate the complete installed graph before committing owner skill changes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_agent.skills.catalog import owner_skill_catalog
from lonora_agent.skills.lifecycle import current_version
from lonora_agent.skills.packages import validate_package_files, validation_image
from lonora_agent.skills.registry import installed_registry
from lonora_agent.workspace import read_snapshot
from lonora_agent.workspace_client import WorkspaceClient
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.skills import (
    AgentSkill,
    SkillCatalog,
    SkillCatalogDetail,
    SkillCatalogEntry,
    SkillRevokeRequest,
    SkillVersionControls,
)
from lonora_core.user_error import LonoraError
from lonora_db.schema import AnalyticalWorkspaceRow, ResourceRow, SkillRow
from lonora_db.skill_controls import read_skill_controls, revoke_skill_version
from lonora_db.skills import SkillRepository
from lonora_db.transactions import owned_agent
from lonora_tools.loader import load_tools
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from . import resource_router


class ValidatedSkillRepository(SkillRepository):
    async def validate_graph(
        self,
        session: AsyncSession,
        owner_id: str,
        agent_id: str | None,
        payload: dict[str, Any] | None,
        exclude_id: str | None = None,
    ) -> None:
        if agent_id:
            await owned_agent(session, owner_id, agent_id, lock=True)
        rows = list(
            await session.scalars(
                select(SkillRow).where(
                    SkillRow.owner_id == owner_id,
                    SkillRow.agent_id == agent_id,
                )
            )
        )
        values = [row.payload for row in rows if row.id != exclude_id]
        if payload is not None:
            validated = AgentSkill.model_validate(payload)
            values.append(validated.model_dump(mode="json"))
        try:
            _, rejected = installed_registry(
                values, {tool.name for tool in load_tools().definitions()}, strict_graph=True
            )
        except LonoraError as error:
            raise LonoraError(error.code, 409) from None
        if payload is not None:
            name = str(payload.get("name", ""))
            reason = rejected.get(name) or rejected.get(name + "@installed")
            if reason and reason not in {"skill_disabled"}:
                raise LonoraError(reason, 422)

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        await self.validate_graph(session, owner_id, agent_id, payload)
        return await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> ResourceRow:
        row = await self.get(session, owner_id, resource_id)
        if row.agent_id:
            await owned_agent(session, owner_id, row.agent_id, lock=True)
        row = await self.get(session, owner_id, resource_id, lock=True)
        if row.version != version:
            raise LonoraError("version_conflict", 409)
        validated = self.validate(payload)
        if "package" in row.state and validated not in (
            row.payload,
            {**row.payload, "enabled": False},
        ):
            # Executable packages need immutable source/validation receipts.
            # Normal owner instructions remain editable; disabling needs no new proof.
            raise LonoraError("skill_package_lifecycle_required", 409)
        await self.validate_graph(session, owner_id, row.agent_id, payload, resource_id)
        return await super().update(session, owner_id, resource_id, payload, version)

    async def delete(self, session: AsyncSession, owner_id: str, resource_id: str) -> None:
        row = await self.get(session, owner_id, resource_id)
        await self.validate_graph(session, owner_id, row.agent_id, None, resource_id)
        await super().delete(session, owner_id, resource_id)


router = APIRouter()
router.include_router(resource_router("/skills", ValidatedSkillRepository()))


async def current_catalog(
    request: Request, agent_id: str, owner_id: str
) -> dict[str, SkillCatalogDetail]:
    async with runtime(request).db.sessions() as session:
        controls = await read_skill_controls(session, owner_id, agent_id)
        rows = (
            await session.scalars(
                select(SkillRow)
                .where(SkillRow.owner_id == owner_id, SkillRow.agent_id == agent_id)
                .order_by(SkillRow.id)
            )
        ).all()
        entries = owner_skill_catalog(
            rows, controls, {tool.name for tool in load_tools().definitions()}
        )
        workspace = None
        pending: dict[str, str] = {}
        by_resource = {item.resource_id: item for item in entries.values() if item.resource_id}
        for row in rows:
            item = by_resource.get(row.id)
            if item is None or not item.available or "package" not in row.state:
                continue
            try:
                _, entry = current_version(row, row.version)
                if workspace is None:
                    workspace = await session.get(AnalyticalWorkspaceRow, agent_id)
                if workspace is None or workspace.active_operation_id:
                    raise LonoraError("skill_package_source_changed", 409)
                validate_package_files(entry, read_snapshot(workspace.snapshot))
                image = validation_image(entry)
                if image is not None:
                    pending[item.id] = image
            except LonoraError as error:
                entries[item.id] = item.model_copy(update={"available": False, "code": error.code})
    # Current owner eligibility consumes the same source/validation checks as
    # Agent admission. Local IPC must not hold a database transaction open.
    if pending:
        profile_code = None
        image = None
        try:
            socket = runtime(request).settings.workspace_socket
            if socket is None:
                raise LonoraError("workspace_execution_unconfigured", 409)
            image = await WorkspaceClient(socket).profile()
        except LonoraError as error:
            profile_code = error.code
        for identity, expected in pending.items():
            if profile_code or expected != image:
                entries[identity] = entries[identity].model_copy(
                    update={
                        "available": False,
                        "code": profile_code or "skill_package_validation_required",
                    }
                )
    return entries


@router.get("/agents/{agent_id}/skills/catalog")
async def catalog(
    request: Request,
    agent_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    owner: OwnerIdentity = Depends(require_owner),
) -> SkillCatalog:
    entries = list((await current_catalog(request, agent_id, owner.id)).values())
    return SkillCatalog(
        agent_id=agent_id,
        items=[
            SkillCatalogEntry.model_validate(item.model_dump(exclude={"content"}))
            for item in entries[offset : offset + limit]
        ],
        total=len(entries),
        next_offset=offset + limit if offset + limit < len(entries) else None,
    )


@router.get("/agents/{agent_id}/skills/catalog/{skill_id}")
async def catalog_detail(
    request: Request,
    agent_id: str,
    skill_id: str,
    owner: OwnerIdentity = Depends(require_owner),
) -> SkillCatalogDetail:
    entries = await current_catalog(request, agent_id, owner.id)
    if skill_id not in entries:
        raise LonoraError("skill_not_found", 404)
    return entries[skill_id]


@router.get("/agents/{agent_id}/skills/revocations")
async def revocations(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> SkillVersionControls:
    async with runtime(request).db.sessions() as session:
        return await read_skill_controls(session, owner.id, agent_id)


@router.post("/agents/{agent_id}/skills/revocations")
async def revoke(
    request: Request,
    agent_id: str,
    body: SkillRevokeRequest,
    owner: OwnerIdentity = Depends(require_owner),
) -> SkillVersionControls:
    async with runtime(request).db.sessions() as session, session.begin():
        return await revoke_skill_version(session, owner.id, agent_id, body)
