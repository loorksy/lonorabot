import base64
from pathlib import Path

from lonora_db.schema import ArtifactRow, MessageRow
from lonora_security.runtime_storage import confined_path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def attachment_context(
    session: AsyncSession, owner_id: str, thread_id: str, input_seq: int, root: Path
) -> tuple[str, list[str]]:
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    notes: list[str] = []
    images: list[str] = []
    if not message:
        return "", images
    for artifact_id in message.attachment_ids:
        artifact = await session.get(ArtifactRow, artifact_id)
        if artifact is None or artifact.owner_id != owner_id:
            continue
        payload = artifact.payload
        path = confined_path(root, payload["key"])
        notes.append("Artifact " + artifact.id + ": " + payload["name"])
        if not path.is_file():
            continue
        media = payload["media_type"]
        if (
            media in {"image/png", "image/jpeg", "image/webp", "image/gif"}
            and path.stat().st_size <= 5 * 1024 * 1024
        ):
            images.append(
                "data:" + media + ";base64," + base64.b64encode(path.read_bytes()).decode()
            )
        elif media.startswith("text/") or media == "application/json":
            notes.append(path.read_text(errors="replace")[:24000])
    return "<untrusted_attachments>\n" + "\n".join(
        notes
    ) + "\n</untrusted_attachments>" if notes else "", images
