from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import ResourceInput, ResourceUpdate
from lonora_db.transactions import ResourceRepository, resource_data

from ..middleware.auth import require_owner, runtime


def resource_router(
    path: str, repository: ResourceRepository, *, omit_catalog_state: tuple[str, ...] = ()
) -> APIRouter:
    router = APIRouter(prefix=path)

    @router.get("")
    async def read_resources(
        request: Request,
        agent_id: str | None = None,
        thread_id: str | None = None,
        owner: OwnerIdentity = Depends(require_owner),
    ) -> list[dict[str, Any]]:
        async with runtime(request).db.sessions() as session:
            rows = await repository.list(session, owner.id, agent_id, thread_id)
            result = [resource_data(row) for row in rows]
            if omit_catalog_state:
                for item in result:
                    item["state"] = {
                        key: value
                        for key, value in item["state"].items()
                        if key not in omit_catalog_state
                    }
            return result

    @router.post("", status_code=201)
    async def create_resource(
        request: Request, body: ResourceInput, owner: OwnerIdentity = Depends(require_owner)
    ) -> dict[str, Any]:
        async with runtime(request).db.sessions() as session, session.begin():
            return resource_data(
                await repository.create(
                    session,
                    owner.id,
                    body.payload,
                    agent_id=body.agent_id,
                    thread_id=body.thread_id,
                )
            )

    @router.get("/{resource_id}")
    async def read_resource(
        request: Request, resource_id: str, owner: OwnerIdentity = Depends(require_owner)
    ) -> dict[str, Any]:
        async with runtime(request).db.sessions() as session:
            return resource_data(await repository.get(session, owner.id, resource_id))

    @router.put("/{resource_id}")
    async def update_resource(
        request: Request,
        resource_id: str,
        body: ResourceUpdate,
        owner: OwnerIdentity = Depends(require_owner),
    ) -> dict[str, Any]:
        async with runtime(request).db.sessions() as session, session.begin():
            return resource_data(
                await repository.update(session, owner.id, resource_id, body.payload, body.version)
            )

    @router.delete("/{resource_id}")
    async def delete_resource(
        request: Request, resource_id: str, owner: OwnerIdentity = Depends(require_owner)
    ) -> dict[str, bool]:
        async with runtime(request).db.sessions() as session, session.begin():
            await repository.delete(session, owner.id, resource_id)
        return {"deleted": True}

    return router
