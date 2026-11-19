import base64
from pathlib import Path
from typing import cast

from lonora_adapter_kit.context_sections import escape_context_text
from lonora_core.user_error import LonoraError
from lonora_db.schema import ArtifactRow, MessageRow
from lonora_security.runtime_storage import confined_path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Scanned pages of one PDF sent as images with the owner's message.
MAX_PAGE_IMAGES = 8


ATTACHMENT_CHARS = 24000


def bounded(text: str, artifact_id: str) -> str:
    """At most ATTACHMENT_CHARS of a file, saying so when the rest is left out, so a
    partial strategy is never taken for the whole one."""
    if len(text) <= ATTACHMENT_CHARS:
        return text
    return (
        text[:ATTACHMENT_CHARS]
        + f"\n[Truncated: {ATTACHMENT_CHARS} of {len(text)} characters shown; "
        + f"artifact_read artifact_id {artifact_id} offset {ATTACHMENT_CHARS} reads the rest.]"
    )


def sidecar(root: Path, key: object) -> Path | None:
    """A stored file the upload wrote beside a PDF; None for anything else."""
    if not isinstance(key, str) or not key:
        return None
    try:
        path = confined_path(root, key)
    except LonoraError:
        return None
    return path if path.is_file() else None


async def third_party_attachment(
    session: AsyncSession, owner_id: str, thread_id: str, input_seq: int
) -> bool:
    """Whether the message carries an attachment: a photo, a text file, a PDF's text layer
    or scanned pages. Only the owner's typed words are the owner's words (6.10, 14.3.8);
    what a file or picture says is someone else's, whoever uploaded it."""
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    for artifact_id in message.attachment_ids if message else []:
        artifact = await session.get(ArtifactRow, artifact_id)
        if artifact is not None and artifact.owner_id == owner_id:
            return True
    return False


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
            notes.append(bounded(path.read_text(errors="replace"), artifact.id))
        # A PDF: the text layer extracted on upload, and the images of scanned pages.
        if text := sidecar(root, payload.get("text_key")):
            notes.append(bounded(text.read_text(errors="replace"), artifact.id))
        page_keys: object = payload.get("page_image_keys")
        listed = cast(list[object], page_keys) if isinstance(page_keys, list) else []
        for image_key in listed[:MAX_PAGE_IMAGES]:
            page = sidecar(root, image_key)
            if page is not None and page.stat().st_size <= 5 * 1024 * 1024:
                images.append(
                    "data:image/jpeg;base64," + base64.b64encode(page.read_bytes()).decode()
                )
    return "\n".join(notes), images
