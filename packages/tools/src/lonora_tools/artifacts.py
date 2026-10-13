import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from lonora_contracts.attachments import ArtifactCreate
from lonora_contracts.domain import Contract
from lonora_core.attachments import check_size, safe_filename
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.runs import require_lease
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path

from .base import Tool
from .context import ToolContext


class ArtifactRead(Contract):
    artifact_id: str


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
    context: ToolContext, name: str, content: bytes, media_type: str
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
        }
        # A stale worker must never replace a file before proving its lease. Replay
        # returns the original bytes; missing files can be repaired from the same hash.
        write_artifact_file(path, content, str(payload["sha256"]))
        return resource_data(row)


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await store_artifact(context, args["name"], args["content"].encode(), args["media_type"])


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await ArtifactRepository().get(session, context.owner_id, args["artifact_id"])
    payload = row.payload
    path = confined_path(context.artifact_root, payload["key"])
    if not path.is_file():
        raise LonoraError("artifact_file_missing", 404)
    result = resource_data(row)
    if payload["media_type"].startswith("text/") or payload["media_type"] == "application/json":
        result["content"] = path.read_text(errors="replace")[:24000]
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
            "Read an owned artifact's metadata and bounded text.",
            ArtifactRead,
            read,
            True,
        ),
    ]
