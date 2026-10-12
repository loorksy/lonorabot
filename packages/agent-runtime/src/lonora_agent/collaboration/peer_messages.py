from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_db.peer_messages import PeerMessageRepository
from lonora_db.runs import create_run, require_lease, run_data
from lonora_db.schema import RunRow
from lonora_db.threads import create_thread
from lonora_db.transactions import owned_agent
from lonora_security.collaboration import require_collaboration
from lonora_tools.context import ToolContext


async def delegate_peer(context: ToolContext, agent_id: str, task: str) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        target = await owned_agent(session, context.owner_id, agent_id)
        require_collaboration(context.owner_id, target.owner_id, context.depth)
        existing = await session.get(RunRow, context.resource_id)
        if existing:
            return run_data(existing)
        thread = await create_thread(
            session, context.owner_id, ThreadCreate(agent_id=agent_id, title=task[:80])
        )
        run = await create_run(
            session,
            context.owner_id,
            RunRequest(
                thread_id=thread.id,
                agent_id=agent_id,
                trigger="peer",
                prompt=task,
                parent_run_id=context.lease.run_id,
                metadata={
                    "depth": context.depth + 1,
                    "return_thread_id": context.thread_id,
                    "return_agent_id": context.agent_id,
                },
            ),
            context.resource_id,
        )
        await PeerMessageRepository().create(
            session,
            context.owner_id,
            {"requester_run_id": context.lease.run_id, "run_id": run.id, "task": task},
            agent_id=agent_id,
            thread_id=thread.id,
            resource_id=context.resource_id,
        )
        return run_data(run)
