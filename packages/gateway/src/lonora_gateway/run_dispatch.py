from pathlib import Path

from lonora_agent.runtime import AgentRuntime
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.runs import claim_next
from lonora_db.schema import ThreadRow

from .runtime import OwnerServices


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
) -> bool:
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
    owner_services = services.get(owner_id)
    if owner_services is None:
        owner_services = OwnerServices.create(
            db, owner_id, key, chart_visual=chart_visual, workspace_socket=workspace_socket
        )
        services[owner_id] = owner_services
    context = owner_services.tool_context(
        agent_id, thread_id, lease, root, depth, maximum_subagents
    )
    await runtime.execute(context)
    return True
