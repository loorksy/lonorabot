import hashlib
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from lonora_contracts.attachments import ArtifactCreate
from lonora_contracts.domain import Contract
from lonora_core.attachments import MAX_ATTACHMENT_BYTES, check_size, safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.runs import require_lease
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path
from PIL import Image, UnidentifiedImageError
from pydantic import Field

from .base import Tool
from .context import ToolContext


class ArtifactRead(Contract):
    artifact_id: str
    view_image: bool = False
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=24000, ge=1, le=24000)


def write_artifact_file(path: Path, content: bytes, digest: str) -> None:
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".partial", delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


async def store_artifact(
    context: ToolContext,
    name: str,
    content: bytes,
    media_type: str,
    *,
    receipt_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    check_size(len(content))
    name = safe_filename(name)
    key = context.resource_id + "/" + name
    path = confined_path(context.artifact_root, key)
    payload = {
        "name": name,
        "key": key,
        "media_type": media_type,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        row = await session.get(ArtifactRepository.row_type, context.resource_id)
        if row is not None:
            if (
                row.owner_id != context.owner_id
                or row.thread_id != context.thread_id
                or row.agent_id != context.agent_id
            ):
                raise LonoraError("artifacts_not_found", 404)
            if receipt_state and any(
                row.state.get(key) != value for key, value in receipt_state.items()
            ):
                raise LonoraError("tool_result_identity_conflict", 409)
            if row.payload != payload:
                raise LonoraError("artifact_nonce_conflict", 409)
        else:
            row = await ArtifactRepository().create(
                session,
                context.owner_id,
                payload,
                agent_id=context.agent_id,
                thread_id=context.thread_id,
                resource_id=context.resource_id,
            )
        row.state = {
            **row.state,
            "producer_run_id": context.lease.run_id,
            "producer_call_id": context.call_id,
            **(receipt_state or {}),
        }
        # A stale worker must never replace a file before proving its lease. Replay
        # returns the original bytes; missing files can be repaired from the same hash.
        write_artifact_file(path, content, str(payload["sha256"]))
        return resource_data(row)


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await store_artifact(context, args["name"], args["content"].encode(), args["media_type"])


MAX_OBSERVATION_BYTES = 5 * 1024 * 1024
RASTER_FORMATS = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def raster_dimensions(content: bytes, media_type: str) -> tuple[int, int]:
    """Shared bounded single-frame raster validation, without trusting a suffix."""
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if not (0 < width <= 4096 and 0 < height <= 4096):
                raise LonoraError("artifact_image_dimensions_exceeded", 413)
            if (
                RASTER_FORMATS.get(image.format or "") != media_type
                or getattr(image, "n_frames", 1) != 1
            ):
                raise LonoraError("artifact_image_format_unsupported", 422)
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise LonoraError("artifact_image_invalid", 422) from None
    return width, height


async def load_image_observation(
    context: ToolContext,
    artifact_id: str,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Resolve only an owned, Agent/thread-scoped immutable raster, never a URL."""
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        row = await ArtifactRepository().get(session, context.owner_id, artifact_id)
    if row.agent_id != context.agent_id or row.thread_id != context.thread_id:
        raise LonoraError("artifacts_not_found", 404)
    payload = row.payload
    media = payload.get("media_type")
    if not isinstance(media, str) or media not in RASTER_FORMATS.values():
        raise LonoraError("artifact_image_format_unsupported", 422)
    try:
        path = confined_path(context.artifact_root, payload["key"])
        if path.stat().st_size > MAX_OBSERVATION_BYTES:
            raise LonoraError("artifact_image_too_large", 413)
        with path.open("rb") as source:
            content = source.read(MAX_OBSERVATION_BYTES + 1)
    except OSError:
        raise LonoraError("artifact_file_missing", 404) from None
    if len(content) > MAX_OBSERVATION_BYTES:
        raise LonoraError("artifact_image_too_large", 413)
    digest = hashlib.sha256(content).hexdigest()
    if (
        digest != payload.get("sha256")
        or len(content) != payload.get("size")
        or (expected_sha256 is not None and digest != expected_sha256)
    ):
        raise LonoraError("artifact_integrity_failed", 409)
    width, height = raster_dimensions(content, media)
    descriptor: dict[str, Any] = {
        "artifact_id": row.id,
        "sha256": digest,
        "media_type": media,
        "width": width,
        "height": height,
        "source": "artifact_store",
    }
    for key in ("producer_run_id", "producer_call_id"):
        value = row.state.get(key)
        if isinstance(value, str) and len(value) <= 200:
            descriptor[key] = value
    snapshot = row.state.get("chart_snapshot")
    if isinstance(snapshot, dict):
        snapshot = cast(dict[str, Any], snapshot)
        descriptor["chart_snapshot"] = {
            key: value
            for key in (
                "source",
                "chart_id",
                "account_id",
                "symbol",
                "timeframe",
                "scene_revision",
                "scene_version",
                "data_revision",
                "source_observed_at",
                "quote_observed_at",
                "scene_updated_at",
                "last_candle_at",
                "captured_at",
                "format",
            )
            if isinstance(value := snapshot.get(key), (str, int))
            and not isinstance(value, bool)
            and len(str(value)) <= 200
        }
    return descriptor, content


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await ArtifactRepository().get(session, context.owner_id, args["artifact_id"])
    internal = row.state.get("internal_tool_result") is True
    if internal and (row.agent_id != context.agent_id or row.thread_id != context.thread_id):
        raise LonoraError("artifacts_not_found", 404)
    payload = row.payload
    path = confined_path(context.artifact_root, payload["key"])
    if not path.is_file():
        raise LonoraError("artifact_file_missing", 404)
    result = resource_data(row)
    if args.get("view_image") is True:
        descriptor, _ = await load_image_observation(context, args["artifact_id"])
        result["image_observation"] = descriptor
    if internal:
        result["state"] = {
            key: value for key, value in row.state.items() if key != "result_summary"
        }
    if payload["media_type"].startswith("text/") or payload["media_type"] == "application/json":
        check_size(path.stat().st_size)
        with path.open("rb") as source:
            content = source.read(MAX_ATTACHMENT_BYTES + 1)
        check_size(len(content))
        if internal and (
            len(content) != payload["size"]
            or hashlib.sha256(content).hexdigest() != payload["sha256"]
        ):
            raise LonoraError("artifact_integrity_failed", 409)
        text = content.decode("utf-8", errors="replace")
        offset, limit = args.get("offset", 0), args.get("limit", 24000)
        result["content"] = text[offset : offset + limit]
        result["total_chars"] = len(text)
        result["next_offset"] = offset + limit if offset + limit < len(text) else None
    return result


def tools() -> list[Tool]:
    return [
        Tool(
            "artifact_create",
            "Create a durable file attached to this thread.",
            ArtifactCreate,
            create,
        ),
        Tool(
            "artifact_read",
            "Read owned artifact metadata and a bounded text page. For a stored tool result use result_ref as artifact_id; offset and limit select characters, next_offset continues paging. Stored results are redacted projections. Set view_image=true to inspect an owned raster image in the next model turn; this returns a validated image reference, never proof of user delivery.",
            ArtifactRead,
            read,
            True,
        ),
    ]
