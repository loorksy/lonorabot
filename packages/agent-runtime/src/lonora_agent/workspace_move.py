"""Each agent's analytical-workspace files, copied once into its home in the owner's
persistent workspace (7.1), under old-workspace/, before the old store is deleted (14.1)."""

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import AnalyticalWorkspaceRow
from lonora_security.secrets import SecretScan
from lonora_workspace.client import WorkspaceClient
from sqlalchemy import select

from .workspace import read_snapshot

DESTINATION = "old-workspace/"
PER_TICK = 5


async def move_snapshots(db: Database, workspace: WorkspaceClient) -> int:
    """Copy up to PER_TICK agents' files; returns how many agents were moved. An agent
    whose copy did not finish is tried again on a later tick; files already copied are
    written again with the same bytes."""
    async with db.sessions() as session:
        rows = (
            await session.scalars(
                select(AnalyticalWorkspaceRow)
                .where(AnalyticalWorkspaceRow.moved_at.is_(None))
                .order_by(AnalyticalWorkspaceRow.agent_id)
                .limit(PER_TICK)
            )
        ).all()
    moved = 0
    for row in rows:
        for path, data in sorted(read_snapshot(row.snapshot).items()):
            # Only the supervisor's acknowledgement comes back; there is nothing to scan.
            written = await workspace.write(SecretScan({}), row.agent_id, DESTINATION + path, data)
            if not written["ok"]:
                raise LonoraError("workspace_snapshot_move_failed", 503)
        async with db.sessions() as session, session.begin():
            current = await session.get(AnalyticalWorkspaceRow, row.agent_id, with_for_update=True)
            # Copied from the bytes read above; a write since then is copied next time.
            if current is not None and current.revision == row.revision:
                current.moved_at = utcnow()
                moved += 1
    return moved
