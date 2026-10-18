import re
from urllib.parse import unquote
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import ArtifactRow, MessageRow, RunRow


async def pending_generated_artifacts(
    session: AsyncSession, owner_id: str, run: RunRow
) -> list[ArtifactRow]:
    """Called under the completion's thread/run locks, including its current lease fence."""
    return list(
        await session.scalars(
            select(ArtifactRow)
            .where(
                or_(
                    ArtifactRow.state["internal_tool_result"].as_boolean().is_(None),
                    ArtifactRow.state["internal_tool_result"].as_boolean().is_(False),
                ),
                ArtifactRow.owner_id == owner_id,
                ArtifactRow.thread_id == run.thread_id,
                ArtifactRow.agent_id == run.agent_id,
                ArtifactRow.state["producer_run_id"].as_string() == run.id,
                ArtifactRow.state["delivered_message_id"].as_string().is_(None),
            )
            .order_by(ArtifactRow.created_at, ArtifactRow.id)
            .with_for_update()
        )
    )


def link_generated_artifacts(message: MessageRow, artifacts: list[ArtifactRow]) -> None:
    """Message attachment IDs and delivery receipts commit in the same transaction."""
    attachment_ids: list[str] = list(message.attachment_ids or [])
    attachment_ids.extend(row.id for row in artifacts)
    message.attachment_ids = list(dict.fromkeys(attachment_ids))
    for artifact in artifacts:
        if not artifact.state.get("delivered_message_id"):
            artifact.state = {**artifact.state, "delivered_message_id": message.id}


async def resolve_reply_artifacts(
    session: AsyncSession, owner_id: str, run: RunRow, answer: str
) -> tuple[str, list[ArtifactRow]]:
    """Resolve known local image references, never arbitrary paths or remote URLs.

    Re-sending a prior image is a new message attachment, not a new producer effect.
    Keep the first delivery receipt for replay and audit.
    """
    artifacts = await pending_generated_artifacts(session, owner_id, run)
    by_id = {artifact.id: artifact for artifact in artifacts}
    # Literal code remains literal; only actual Markdown image references are delivery intent.
    blocks = re.split(r"(```[\s\S]*?```|`[^`\n]*`)", answer)
    pattern = re.compile(r"!\[[^\]\n]*\]\((?:sandbox:)?/mnt/data/([^\s)]+)\)")
    resolved = False
    remaining = 20
    for index in range(0, len(blocks), 2):
        block = blocks[index]
        matches = list(pattern.finditer(block))[:remaining]
        remaining -= len(matches)
        for match in matches:
            key = unquote(match.group(1))
            identity, separator, _ = key.partition("/")
            try:
                artifact_id = str(UUID(identity))
            except ValueError:
                continue
            if not separator:
                continue
            artifact = await session.scalar(
                select(ArtifactRow)
                .where(
                    ArtifactRow.id == artifact_id,
                    ArtifactRow.owner_id == owner_id,
                    ArtifactRow.thread_id == run.thread_id,
                    ArtifactRow.agent_id == run.agent_id,
                )
                .with_for_update()
            )
            if (
                artifact is None
                or artifact.payload.get("key") != key
                or not str(artifact.payload.get("media_type", "")).startswith("image/")
            ):
                continue
            by_id[artifact.id] = artifact
            resolved = True
            block = block.replace(match.group(0), "")
        blocks[index] = block
    return ("".join(blocks).strip() if resolved else answer), list(by_id.values())
