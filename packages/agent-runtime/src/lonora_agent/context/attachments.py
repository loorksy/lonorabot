import base64
from pathlib import Path

from lonora_adapter_kit.context_sections import escape_context_text
from lonora_db.schema import ArtifactRow, MessageRow
from lonora_security.runtime_storage import confined_path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Scanned pages of one PDF sent as images with the owner's message.
MAX_PAGE_IMAGES = 8


async def attachment_context(
    session: AsyncSession, owner_id: str, thread_id: str, input_seq: int, root: Path
) -> tuple[str, list[str]]:
    """Attachment text wrapped and escaped for an owner message (steering)."""
    notes, images = await attachment_parts(session, owner_id, thread_id, input_seq, root)
    return (
        "<untrusted_attachments>\n" + escape_context_text(notes) + "\n</untrusted_attachments>"
        if notes
        else "",
        images,
    )


async def attachment_parts(
    session: AsyncSession, owner_id: str, thread_id: str, input_seq: int, root: Path
) -> tuple[str, list[str]]:
    """Raw attachment names and text, plus image payloads, for one input message."""
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
        # A PDF: the text layer extracted on upload, and the images of scanned pages.
        if text_key := payload.get("text_key"):
            text = confined_path(root, text_key)
            if text.is_file():
                notes.append(text.read_text(errors="replace")[:24000])
        for image_key in payload.get("page_image_keys", [])[:MAX_PAGE_IMAGES]:
            page = confined_path(root, image_key)
            if page.is_file() and page.stat().st_size <= 5 * 1024 * 1024:
                images.append(
                    "data:image/jpeg;base64," + base64.b64encode(page.read_bytes()).decode()
                )
    return "\n".join(notes), images
