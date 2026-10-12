import hashlib
import os
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


async def store_artifact(
    context: ToolContext, name: str, content: bytes, media_type: str
) -> dict[str, Any]:
    check_size(len(content))
    name = safe_filename(name)
    key = context.resource_id + "/" + name
    path = confined_path(context.artifact_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(content)
    os.replace(temporary, path)
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
        row = row or await ArtifactRepository().create(
            session,
            context.owner_id,
            payload,
            agent_id=context.agent_id,
            thread_id=context.thread_id,
            resource_id=context.resource_id,
        )
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
