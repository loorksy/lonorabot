"""Where an agent's skill-package files are kept: its private package store (the table
of the former analytical workspace, kept for this). Packages are private to the agent
(3.2.1); the owner's workspace is shared by all agents (7.1), so files are only copied
there to run a utility. The store's revision is internal and never asked of the model."""

from lonora_contracts.domain import utcnow
from lonora_db.schema import AnalyticalWorkspaceRow
from sqlalchemy.ext.asyncio import AsyncSession

from ..workspace import encode_snapshot, read_snapshot


async def stored_files(session: AsyncSession, agent_id: str) -> dict[str, bytes]:
    row = await session.get(AnalyticalWorkspaceRow, agent_id)
    return read_snapshot(row.snapshot) if row is not None else {}


async def store_files(session: AsyncSession, agent_id: str, files: dict[str, str]) -> None:
    """Add files to the agent's store, in the caller's transaction; quotas as before."""
    row = await session.get(AnalyticalWorkspaceRow, agent_id, with_for_update=True)
    if row is None:
        row = AnalyticalWorkspaceRow(agent_id=agent_id, revision=0, snapshot=b"{}")
        session.add(row)
        await session.flush()
    current = read_snapshot(row.snapshot)
    current.update({path: body.encode() for path, body in files.items()})
    row.snapshot = encode_snapshot(current)
    row.revision += 1
    row.updated_at = utcnow()
