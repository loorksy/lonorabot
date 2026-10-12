import hashlib
from typing import Any

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import new_id
from lonora_core.attachments import check_size, safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/artifacts", ArtifactRepository())


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(),
    thread_id: str | None = Form(default=None),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    artifact_id = new_id()
    name = safe_filename(file.filename or artifact_id)
    content = await file.read(20 * 1024 * 1024 + 1)
    check_size(len(content))
    key = artifact_id + "/" + name
    path = confined_path(rt.settings.artifact_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    async with rt.db.sessions() as session, session.begin():
        return resource_data(
            await ArtifactRepository().create(
                session,
                owner.id,
                {
                    "name": name,
                    "key": key,
                    "size": len(content),
                    "media_type": file.content_type or "application/octet-stream",
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                thread_id=thread_id,
                resource_id=artifact_id,
            )
        )


@router.get("/{artifact_id}/file")
async def download(
    request: Request,
    artifact_id: str,
    preview: bool = False,
    owner: OwnerIdentity = Depends(require_owner),
) -> FileResponse:
    async with runtime(request).db.sessions() as session:
        row = await ArtifactRepository().get(session, owner.id, artifact_id)
    path = confined_path(runtime(request).settings.artifact_root, row.payload["key"])
    if not path.is_file():
        raise LonoraError("artifact_file_missing", 404)
    return FileResponse(
        path,
        media_type=row.payload["media_type"],
        filename=row.payload["name"],
        content_disposition_type="inline"
        if preview
        and row.payload["media_type"]
        in {
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif",
            "application/pdf",
            "text/html",
            "image/svg+xml",
        }
        else "attachment",
        headers={
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )
