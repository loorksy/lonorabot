import hashlib
from pathlib import Path
from typing import Any

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract, new_id, utcnow
from lonora_core.attachments import check_size, safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.events import emit
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path
from pydantic import Field

from ..middleware.auth import require_owner, runtime
from ..pdf_layers import extract, is_pdf
from . import resource_router

router = resource_router("/artifacts", ArtifactRepository())


def upload_type(content_type: str | None, name: str) -> str:
    """A text file the browser could not type (empty, octet-stream) is stored as text/plain."""
    if content_type and content_type != "application/octet-stream":
        return content_type
    return "text/plain" if name.lower().endswith(TEXT_SUFFIXES) else "application/octet-stream"


async def pdf_sidecars(root: Path, key: str, content: bytes) -> dict[str, Any]:
    """The PDF's text layer and scanned page images, stored beside it for agents to read."""
    layers = await extract(content)
    found: dict[str, Any] = {}
    if layers.text:
        text_key = key + ".text"
        confined_path(root, text_key).write_text(layers.text, encoding="utf-8")
        found["text_key"], found["text_chars"] = text_key, len(layers.text)
    if layers.images:
        keys = [f"{key}.page-{index}.jpg" for index in range(1, len(layers.images) + 1)]
        for image_key, image in zip(keys, layers.images, strict=True):
            confined_path(root, image_key).write_bytes(image)
        found["page_image_keys"] = keys
    return found


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(),
    thread_id: str | None = Form(default=None),
    agent_id: str | None = Form(default=None),
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
    media_type = upload_type(file.content_type, name)
    payload: dict[str, Any] = {
        "name": name,
        "key": key,
        "size": len(content),
        "media_type": media_type,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    if is_pdf(media_type, name):
        payload.update(await pdf_sidecars(rt.settings.artifact_root, key, content))
    async with rt.db.sessions() as session, session.begin():
        return resource_data(
            await ArtifactRepository().create(
                session,
                owner.id,
                payload,
                agent_id=agent_id,
                thread_id=thread_id,
                resource_id=artifact_id,
            )
        )


TEXT_TYPES = {"application/json", "application/xml", "application/x-ndjson"}
# The same list as the web's «الملفات» (FilesPages.tsx TEXT_NAME).
TEXT_SUFFIXES = (
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".html",
    ".css",
    ".js",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
)
MAX_TEXT_BYTES = 600_000


def is_text(media_type: str, name: str = "") -> bool:
    kind = media_type.split(";")[0].strip()
    return kind in TEXT_TYPES or kind.startswith("text/") or name.lower().endswith(TEXT_SUFFIXES)


class TextContent(Contract):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=MAX_TEXT_BYTES)


@router.put("/{artifact_id}/text")
async def save_text(
    request: Request,
    artifact_id: str,
    body: TextContent,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """«تحرير الملف» (Q36): the owner rewrites a text file; other files are not editable.

    Each save writes a new file under this artifact's own folder and only after the row is
    committed removes the previous one, and only when it lies in that same folder: a
    failed save keeps the last committed bytes, and no stored key reaches another file.
    """
    rt = runtime(request)
    name = safe_filename(body.name)
    content = body.content.encode()
    if len(content) > MAX_TEXT_BYTES:
        raise LonoraError("attachment_too_large", 413)
    folder = artifact_id + "/"
    async with rt.db.sessions() as session, session.begin():
        row = await ArtifactRepository().get(session, owner.id, artifact_id, lock=True)
        if row.version != body.expected_version:
            raise LonoraError("version_conflict", 409)
        if not is_text(str(row.payload.get("media_type", "")), str(row.payload.get("name", ""))):
            raise LonoraError("artifact_not_text", 409)
        previous = str(row.payload.get("key", ""))
        key = f"{folder}v{row.version + 1}/{name}"
        path = confined_path(rt.settings.artifact_root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        row.payload = {
            **row.payload,
            "name": name,
            "key": key,
            "media_type": "text/plain"
            if not is_text(str(row.payload.get("media_type", "")))
            else row.payload["media_type"],
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        row.version += 1
        row.updated_at = utcnow()
        emit(
            session,
            owner.id,
            "artifacts.updated",
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload={"id": row.id, "version": row.version},
        )
        saved = resource_data(row)
    if previous != key and previous.startswith(folder) and ".." not in previous.split("/"):
        confined_path(rt.settings.artifact_root, previous).unlink(missing_ok=True)
    return saved


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
