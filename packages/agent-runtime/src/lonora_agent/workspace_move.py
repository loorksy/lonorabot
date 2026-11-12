"""Each agent's analytical-workspace files, copied once into its home in the owner's
persistent workspace (7.1), under old-workspace/, before the old store is deleted (14.1)."""

import logging

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import AnalyticalWorkspaceRow
from lonora_security.secrets import SecretScan
from lonora_workspace.client import WorkspaceClient
from sqlalchemy import select

from .workspace import read_snapshot

DESTINATION = "old-workspace/"
PER_TICK = 5
log = logging.getLogger("lonora.workspace.move")


async def move_snapshots(db: Database, workspace: WorkspaceClient) -> int:
    """Copy up to PER_TICK agents' files, least recently tried first; returns how many
    agents were moved. An agent whose copy did not finish is tried again after the
    others; files already copied are written again with the same bytes. An unreachable
    supervisor ends the tick (its error propagates)."""
    async with db.sessions() as session, session.begin():
        rows = (
            await session.scalars(
                select(AnalyticalWorkspaceRow)
                .where(AnalyticalWorkspaceRow.moved_at.is_(None))
                .order_by(
                    AnalyticalWorkspaceRow.move_tried_at.asc().nulls_first(),
                    AnalyticalWorkspaceRow.agent_id,
                )
                .limit(PER_TICK)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            row.move_tried_at = utcnow()
        tried = [(row.agent_id, row.revision, row.snapshot) for row in rows]
    moved = 0
    for agent_id, revision, snapshot in tried:
        failed = None
        for path, data in sorted(read_snapshot(snapshot).items()):
            # Only the supervisor's acknowledgement comes back; there is nothing to scan.
            written = await workspace.write(SecretScan({}), agent_id, DESTINATION + path, data)
            if not written["ok"]:
                failed = path
                break
        if failed is not None:
            log.warning("workspace_snapshot_move_failed agent_id=%s", agent_id)
            continue
        async with db.sessions() as session, session.begin():
            current = await session.get(AnalyticalWorkspaceRow, agent_id, with_for_update=True)
            # Copied from the bytes read above; a write since then is copied next time.
            if current is not None and current.revision == revision:
                current.moved_at = utcnow()
                moved += 1
    return moved
