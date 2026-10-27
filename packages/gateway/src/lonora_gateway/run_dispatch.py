import logging
from pathlib import Path
from time import perf_counter

from lonora_agent.runtime import AgentRuntime
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.runs import aware, claim_next
from lonora_db.schema import ThreadRow
from lonora_logging.correlation import correlate_run

from .runtime import OwnerServices

log = logging.getLogger("lonora.chat")


async def dispatch_one(
    db: Database,
    identity: str,
    runtime: AgentRuntime,
    services: dict[str, OwnerServices],
    key: str,
    root: Path,
    lease_seconds: int,
    maximum_subagents: int,
    lane: str | None = None,
    chart_visual: ChartVisualRuntime | None = None,
    workspace_socket: Path | None = None,
    mcp_declarations: tuple[McpToolDeclaration, ...] = (),
) -> bool:
    dispatch_started = perf_counter()
    async with db.sessions() as session, session.begin():
        run = await claim_next(session, identity, lease_seconds, lane)
        if run is None:
            return False
        thread = await session.get(ThreadRow, run.thread_id)
        if thread is None:
            return False
        owner_id = thread.owner_id
        lease = Lease(run_id=run.id, owner=identity, fence=run.lease_fence)
        agent_id, thread_id, depth = (
            run.agent_id,
            run.thread_id,
            int(run.model_metadata.get("depth", 0)),
        )
        age_ms = round((aware(run.updated_at) - aware(run.created_at)).total_seconds() * 1000, 2)
        # A resumed Task can be days old; its lifetime is not queue delay.
        queue_ms = age_ms if run.lease_fence == 1 else None
    owner_services = services.get(owner_id)
    if owner_services is None:
        owner_services = OwnerServices.create(
            db,
            owner_id,
            key,
            chart_visual=chart_visual,
            workspace_socket=workspace_socket,
            mcp_declarations=mcp_declarations,
        )
        services[owner_id] = owner_services
    context = owner_services.tool_context(
        agent_id, thread_id, lease, root, depth, maximum_subagents
    )
    with correlate_run(lease.run_id):
        log.info(
            "run_dispatch queue_ms=%s run_age_ms=%.2f dispatch_ms=%.2f lane=%s",
            queue_ms,
            age_ms,
            (perf_counter() - dispatch_started) * 1000,
            lane or "shared",
        )
        await runtime.execute(context)
    return True
