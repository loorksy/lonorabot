"""Publish exact saved analytical bytes through the existing artifact lifecycle."""

import asyncio
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from lonora_core.attachments import safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.schema import AnalyticalWorkspaceRow, ArtifactRow
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path
from lonora_session.idempotency import request_hash
from lonora_tools.artifacts import raster_dimensions, store_artifact
from lonora_tools.context import ToolContext

from .workspace import MAX_FILE_BYTES, encode_snapshot, read_snapshot
from .workspace_access import scoped_run

TEXT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
}
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def export_media(path: str, content: bytes) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in IMAGE_TYPES:
        raster_dimensions(content, IMAGE_TYPES[suffix])
        return IMAGE_TYPES[suffix]
    if suffix in TEXT_TYPES:
        try:
            content.decode("utf-8")
            if suffix == ".json":
                json.loads(content)
        except (UnicodeError, ValueError, RecursionError):
            raise LonoraError("workspace_export_format_invalid", 422) from None
        return TEXT_TYPES[suffix]
    raise LonoraError("workspace_export_format_unsupported", 422)


def verify_export(path: Path, payload: dict[str, Any]) -> None:
    try:
        with path.open("rb") as source:
            body = source.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise LonoraError("artifact_file_missing", 404) from None
    if (
        len(body) != payload.get("size")
        or len(body) > MAX_FILE_BYTES
        or hashlib.sha256(body).hexdigest() != payload.get("sha256")
    ):
        raise LonoraError("artifact_integrity_failed", 409)


async def export_file(
    context: ToolContext, path: str, revision: int, name: str | None
) -> dict[str, Any]:
    encode_snapshot({path: b""})
    destination = name or PurePosixPath(path).name
    if safe_filename(destination) != destination:
        raise LonoraError("workspace_export_filename_invalid", 422)
    source_suffix, destination_suffix = (
        PurePosixPath(path).suffix.lower(),
        PurePosixPath(destination).suffix.lower(),
    )
    if destination_suffix != source_suffix and not {destination_suffix, source_suffix} <= {
        ".jpg",
        ".jpeg",
    }:
        raise LonoraError("workspace_export_format_mismatch", 422)
    digest = request_hash(
        {"kind": "workspace_export_v1", "path": path, "revision": revision, "name": destination}
    )
    original: dict[str, Any] | None = None
    async with context.db.sessions() as session, session.begin():
        await scoped_run(session, context, mutate=True)
        existing = await session.get(ArtifactRow, context.resource_id)
        if existing is not None:
            if (
                existing.owner_id != context.owner_id
                or existing.agent_id != context.agent_id
                or existing.thread_id != context.thread_id
            ):
                raise LonoraError("artifacts_not_found", 404)
            if (
                existing.state.get("workspace_export_identity") != digest
                or existing.state.get("producer_run_id") != context.lease.run_id
                or existing.state.get("producer_call_id") != context.call_id
            ):
                raise LonoraError("workspace_export_conflict", 409)
            original = resource_data(existing)
            content = b""
        else:
            workspace = await session.get(AnalyticalWorkspaceRow, context.agent_id)
            if (workspace.revision if workspace else 0) != revision:
                raise LonoraError("workspace_revision_conflict", 409)
            files = read_snapshot(workspace.snapshot) if workspace else {}
            if path not in files:
                raise LonoraError("workspace_file_not_found", 404)
            content = files[path]
    if original is not None:
        artifact_path = confined_path(context.artifact_root, original["payload"]["key"])
        await asyncio.to_thread(verify_export, artifact_path, original["payload"])
        async with context.db.sessions() as session, session.begin():
            await scoped_run(session, context, mutate=True)
        return original
    media = await asyncio.to_thread(export_media, path, content)
    return await store_artifact(
        context,
        destination,
        content,
        media,
        receipt_state={
            "workspace_export_identity": digest,
            "workspace_source": {
                "path": path,
                "revision": revision,
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        },
    )
