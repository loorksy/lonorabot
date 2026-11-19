"""Each agent's analytical-workspace files, copied once into its home in the owner's
persistent workspace (7.1), under old-workspace/, before the old store is deleted (14.1)."""

import base64
import json
import logging
from typing import cast

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import AnalyticalWorkspaceRow
from lonora_security.secrets import SecretScan
from lonora_workspace.client import WorkspaceClient
from sqlalchemy import select
from sqlalchemy import true as sa_true

from .skills.paths import check_files, package_path

DESTINATION = "old-workspace/"


def read_snapshot(content: bytes) -> dict[str, bytes]:
    """The former analytical workspace's files: a JSON object of path to base64 bytes,
    checked as the old store checked an export (no duplicate path, string bodies, bounds)."""
    if len(content) > MAX_TRANSFER_BYTES:
        raise LonoraError("workspace_snapshot_too_large", 422)

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise LonoraError("workspace_path_duplicate", 422)
            result[key] = value
        return result

    try:
        value: object = json.loads(bytes(content) or b"{}", object_pairs_hook=pairs)
        if not isinstance(value, dict):
            raise ValueError
        files: dict[str, bytes] = {}
        for name, body in cast(dict[str, object], value).items():
            if not isinstance(body, str):
                raise ValueError
            files[package_path(name)] = base64.b64decode(body, validate=True)
    except (ValueError, TypeError, RecursionError):
        raise LonoraError("workspace_snapshot_invalid", 422) from None
    check_files(files)
    return files


PER_TICK = 5
# The old store's bound on one exported snapshot.
MAX_TRANSFER_BYTES = 12 * 1024 * 1024
log = logging.getLogger("lonora.workspace.move")


async def move_snapshots(
    db: Database, workspace: WorkspaceClient, unreadable: set[str] | None = None
) -> int:
    """Copy up to PER_TICK agents' files, least recently tried first; returns how many
    agents were moved. An agent whose copy did not finish is tried again after the
    others; files already copied are written again with the same bytes. An unreachable
    supervisor ends the tick (its error propagates). A snapshot that cannot be read is
    logged once and left in the database: `unreadable` (kept by the caller) holds those
    agents, so later ticks skip them."""
    skipped = unreadable if unreadable is not None else set[str]()
    async with db.sessions() as session, session.begin():
        rows = (
            await session.scalars(
                select(AnalyticalWorkspaceRow)
                .where(
                    AnalyticalWorkspaceRow.moved_at.is_(None),
                    AnalyticalWorkspaceRow.agent_id.not_in(skipped) if skipped else sa_true(),
                )
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
        try:
            files = read_snapshot(snapshot)
        except LonoraError as error:
            # A stored snapshot that cannot be read is never moved; the others go on.
            log.warning("workspace_snapshot_unreadable agent_id=%s code=%s", agent_id, error.code)
            skipped.add(agent_id)
            continue
        for path, data in sorted(files.items()):
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
