"""A file in the owner's workspace delivered to the chat as a real attachment (7.1)."""

import asyncio
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from lonora_contracts.domain import Contract
from lonora_core.attachments import safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.schema import ArtifactRow
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path
from lonora_session.idempotency import request_hash
from pydantic import Field

from .artifacts import raster_dimensions, store_artifact
from .base import Tool
from .context import ToolContext
from .terminal import FILE_LIMIT, available, client, scan

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


class ExportInput(Contract):
    path: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, min_length=1, max_length=160)


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


def destination_name(path: str, name: str | None) -> str:
    destination = name or PurePosixPath(path).name
    if safe_filename(destination) != destination:
        raise LonoraError("workspace_export_filename_invalid", 422)
    source, target = PurePosixPath(path).suffix.lower(), PurePosixPath(destination).suffix.lower()
    if source not in TEXT_TYPES and source not in IMAGE_TYPES:
        raise LonoraError("workspace_export_format_unsupported", 422)
    if target != source and not {target, source} <= {".jpg", ".jpeg"}:
        raise LonoraError("workspace_export_format_mismatch", 422)
    return destination


def verify_export(path: Path, payload: dict[str, Any]) -> None:
    try:
        with path.open("rb") as source:
            body = source.read(FILE_LIMIT + 1)
    except OSError:
        raise LonoraError("artifact_file_missing", 404) from None
    if len(body) != payload.get("size") or hashlib.sha256(body).hexdigest() != payload.get(
        "sha256"
    ):
        raise LonoraError("artifact_integrity_failed", 409)


async def export(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    request = ExportInput.model_validate(arguments)
    destination = destination_name(request.path, request.name)
    identity = request_hash(
        {"kind": "workspace_export_v2", "path": request.path, "name": destination}
    )
    # A replay of the same call returns the attachment it made, even if the file changed.
    original: dict[str, Any] | None = None
    async with context.db.sessions() as session:
        existing = await session.get(ArtifactRow, context.resource_id)
        if existing is not None:
            if (
                existing.owner_id != context.owner_id
                or existing.agent_id != context.agent_id
                or existing.thread_id != context.thread_id
            ):
                raise LonoraError("artifacts_not_found", 404)
            if (
                existing.state.get("workspace_export_identity") != identity
                or existing.state.get("producer_run_id") != context.lease.run_id
                or existing.state.get("producer_call_id") != context.call_id
            ):
                raise LonoraError("workspace_export_conflict", 409)
            original = resource_data(existing)
    if original is not None:
        artifact = confined_path(context.artifact_root, original["payload"]["key"])
        await asyncio.to_thread(verify_export, artifact, original["payload"])
        return original
    # The whole file is refused if any secret form is in it: what reaches the chat
    # carries no secret, and a replaced value would change the owner's file.
    content = await client(context).read_bytes(await scan(context), context.agent_id, request.path)
    media = await asyncio.to_thread(export_media, request.path, content)
    return await store_artifact(
        context,
        destination,
        content,
        media,
        receipt_state={
            "workspace_export_identity": identity,
            "workspace_source": {
                "path": request.path,
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        },
    )


def tools() -> list[Tool]:
    return [
        Tool(
            "workspace_export",
            "Send a workspace file to the chat as a real attachment: UTF-8 TXT/MD/CSV/TSV/JSON"
            " or a single-frame PNG/JPEG/WEBP/GIF up to 2 MiB (relative paths start in your"
            " home). A file holding a secret is refused. Replays return the original"
            " attachment. Export alone does not prove visual inspection or user receipt; use"
            " artifact_read with view_image=true before making visual claims.",
            ExportInput,
            export,
            replay_safe=True,
            timeout_seconds=120,
            availability=available,
            search_terms="attach send file report chart image export إرسال ملف",
        ),
    ]
