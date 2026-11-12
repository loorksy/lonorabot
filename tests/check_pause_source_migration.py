"""Migration 0155: a pause made from the owner's message becomes the owner's (mandate 4.7.2).

On a disposable PostgreSQL at head: step down below 0155, record a live hold with the
old ``owner_message`` source and an agent's own hold, step up again. The first is the
owner's now (holder and message kept), the second is unchanged, and the CHECK refuses
the old source. The downgrade keeps the owner's pause the owner's, and the upgrade runs
again cleanly.
"""

import asyncio
import subprocess
import sys
from uuid import uuid4

from check_trading import database
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_db.agents import create_agent
from lonora_db.schema import OwnerRow, SupervisionHoldRow
from sqlalchemy import delete, select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0061_trade_approval_validity"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="pause-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        holder = await create_agent(session, owner_id, AgentCreate(name="Holder " + uuid4().hex))
        paused = await create_agent(session, owner_id, AgentCreate(name="Paused " + uuid4().hex))
        holder_id, paused_id = holder.id, paused.id
    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    asked, own = str(uuid4()), str(uuid4())
    async with db.sessions() as session, session.begin():
        for identifier, kind, source in ((asked, "agent", "owner_message"), (own, "task", "agent")):
            await session.execute(
                text(
                    "INSERT INTO ln_supervision_holds (id, owner_id, holder_agent_id, agent_id,"
                    " target_kind, target_id, source, created_at) VALUES (:id, :owner, :holder,"
                    " :agent, :kind, :target, :source, :at)"
                ),
                {
                    "id": identifier,
                    "owner": owner_id,
                    "holder": holder_id,
                    "agent": paused_id,
                    "kind": kind,
                    "target": paused_id if kind == "agent" else str(uuid4()),
                    "source": source,
                    "at": utcnow(),
                },
            )
    await db.engine.dispose()
    alembic("upgrade", "head")
    async with db.sessions() as session:
        rows = {
            row.id: row
            for row in await session.scalars(
                select(SupervisionHoldRow).where(SupervisionHoldRow.id.in_([asked, own]))
            )
        }
        assert rows[asked].source == "owner" and rows[asked].holder_agent_id == holder_id
        assert rows[own].source == "agent"
    try:
        async with db.sessions() as session, session.begin():
            await session.execute(
                text("UPDATE ln_supervision_holds SET source = 'owner_message' WHERE id = :id"),
                {"id": own},
            )
    except Exception as error:  # noqa: BLE001 - the CHECK constraint's IntegrityError
        assert "ln_supervision_hold_source" in str(error), error
    else:
        raise AssertionError("the old owner_message source was accepted")
    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    async with db.sessions() as session:
        source = await session.scalar(
            text("SELECT source FROM ln_supervision_holds WHERE id = :id"), {"id": asked}
        )
        assert source == "owner", source
    await db.engine.dispose()
    alembic("upgrade", "head")
    async with db.sessions() as session, session.begin():
        await session.execute(
            delete(SupervisionHoldRow).where(SupervisionHoldRow.id.in_([asked, own]))
        )
    await db.engine.dispose()
    print("PASS 0155: owner_message holds are the owner's; the downgrade never weakens a pause")


if __name__ == "__main__":
    asyncio.run(main())
