import asyncio
from uuid import uuid4
from sqlalchemy import select, func
import check_authority_migration as c
from lonora_db.schema import RunRow, TicketRow, SupervisionHoldRow, OwnerRow

async def main():
    db = c.database()
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email="repro@example.test", password_hash="x")
        session.add(owner); await session.flush()
        seed = c.Seed(session, owner.id, "")
        held = await seed.agent("Held", role="general", scope_mode="flexible")
        boss = await seed.agent("Boss", role="general", scope_mode="flexible")
        out = {}
        # A: paused Task whose Run was cancelled (no failure recorded); B: Run failed, no failure
        for name, rs in (("cancelled_run", "cancelled"), ("failed_run", "failed")):
            thread = await seed.conversation(held.id)
            run = RunRow(thread_id=thread.id, agent_id=held.id, trigger="tickets", status=rs)
            session.add(run); await session.flush()
            task = await seed.task(held.id, thread.id, str(uuid4()), status="paused")
            hold = await seed.hold(held.id, "task", task.id, "agent", boss.id)
            out[name] = (task.id, thread.id, hold.id)
    await c.upgrade_from(db, c.BEFORE)
    async with db.sessions() as session:
        for name, (tid, th, hid) in out.items():
            t = await session.get(TicketRow, tid); h = await session.get(SupervisionHoldRow, hid)
            n = await session.scalar(select(func.count()).select_from(RunRow).where(RunRow.thread_id == th))
            print(name, "hold released:", h.released_at is not None, "task status:", t.state["task"]["status"], "runs in thread:", n)
asyncio.run(main())
