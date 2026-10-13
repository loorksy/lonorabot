from sqlalchemy import select
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
        artifact.state = {**artifact.state, "delivered_message_id": message.id}
