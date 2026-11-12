import asyncio
from uuid import uuid4
from sqlalchemy import select
import check_authority_migration as c
from lonora_contracts.tasks import TaskFailure
from lonora_db.schema import RunRow, TicketRow, OwnerRow
from lonora_db.supervision import work_paused

async def main():
    db = c.database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        seed = c.Seed(session, owner.id, "")
        held = await seed.agent("Held2", role="general", scope_mode="flexible")
        boss = await seed.agent("Boss2", role="general", scope_mode="flexible")
        thread = await seed.conversation(held.id)
        run = RunRow(thread_id=thread.id, agent_id=held.id, trigger="tickets", status="failed")
        session.add(run); await session.flush()
        task = await seed.task(held.id, thread.id, str(uuid4()), status="failed")
        f = TaskFailure(run_id=run.id, lease_fence=1, code="broker_down", attempt=1, recovery="owner").model_dump(mode="json")
        task.state = {"task": {**task.state["task"], "failure": f}}
        await seed.hold(held.id, "task", task.id, "agent", boss.id)
        await session.flush()
        print("live work_paused:", await work_paused(session, "task", task.id))
        tid, th = task.id, thread.id
    await c.upgrade_from(db, c.BEFORE)
    async with db.sessions() as session:
        runs = list(await session.scalars(select(RunRow).where(RunRow.thread_id == th)))
        print("runs:", [(r.trigger, r.status) for r in runs])
asyncio.run(main())
