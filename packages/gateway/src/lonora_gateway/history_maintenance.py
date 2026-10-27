"""Optional summaries run outside conversation workers and execution leases."""

import logging
from pathlib import Path

from lonora_agent.context.compaction import compact_history
from lonora_contracts.runs import Lease
from lonora_db.schema import RunRow, ThreadRow
from sqlalchemy import select

from .runtime import OwnerServices

log = logging.getLogger("lonora.chat")


async def maintain_history(service: OwnerServices, root: Path) -> None:
    # Bounded projection, never checkpoint bodies or a scan of the event ledger.
    # Expensive work only begins at the compactor's unsummarized-history limit.
    async with service.db.sessions() as session:
        rows = (
            await session.execute(
                select(
                    RunRow.id,
                    RunRow.thread_id,
                    RunRow.agent_id,
                    RunRow.lease_owner,
                    RunRow.lease_fence,
                )
                .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
                .where(
                    ThreadRow.owner_id == service.owner_id,
                    ThreadRow.purpose == "conversation",
                    RunRow.status == "completed",
                )
                .order_by(RunRow.created_at.desc())
                .limit(50)
            )
        ).all()
    seen: set[str] = set()
    for row in rows:
        if row.thread_id in seen or not row.lease_owner:
            continue
        seen.add(row.thread_id)
        context = service.tool_context(
            row.agent_id,
            row.thread_id,
            Lease(run_id=row.id, owner=row.lease_owner, fence=row.lease_fence),
            root,
        )
        try:
            await compact_history(context, settled=True)
        except Exception as error:
            # Optional archive failure cannot fail a committed reply or prevent
            # another conversation from being served by a foreground worker.
            log.warning("history_maintenance_failed type=%s", type(error).__name__)
        if len(seen) >= 5:
            break
