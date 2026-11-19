"""Migration 0102: stored v2 cards of kind ``receipt`` become ``summary`` (mandate 10.3).

On a disposable PostgreSQL at head: step down below 0102, store an assistant message
whose card has the old kind (as the previous release wrote it) next to one of another
kind, step up. The old card is now ``summary``, still validates as rich content, and
nothing else in either message changed. The downgrade restores the old kind.
"""

import asyncio
import subprocess
import sys
from typing import Any

from check_trading import database
from lonora_contracts.visual_response import RichContent
from lonora_db.schema import AgentRow, MessageRow, OwnerRow, RunRow, ThreadRow
from sqlalchemy import select

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0131_agent_model_owner_only"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def card(kind: str) -> dict[str, Any]:
    return {
        "version": 1,
        "parts": [
            {"type": "text", "text": "The alert is active."},
            {
                "type": "ui",
                "document": {
                    "v": 2,
                    "kind": kind,
                    "title": "Alert active",
                    "icon": "check",
                    "facts": {},
                    "state": {},
                    "calc": {},
                    "blocks": [{"type": "Text", "text": "Gold above 2,400"}],
                    "fallback": "Gold above 2,400",
                    "why": "w",
                },
            },
        ],
    }


async def kinds(db: Any, ids: list[str]) -> list[str]:
    async with db.sessions() as session:
        rows = {
            row.id: row
            for row in await session.scalars(select(MessageRow).where(MessageRow.id.in_(ids)))
        }
        return [rows[i].rich_content["parts"][1]["document"]["kind"] for i in ids]


async def main() -> None:
    db = database()
    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="summary-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        thread = ThreadRow(owner_id=owner.id)
        session.add(thread)
        await session.flush()
        old = MessageRow(
            thread_id=thread.id, seq=1, role="assistant", content="a", rich_content=card("receipt")
        )
        other = MessageRow(
            thread_id=thread.id, seq=2, role="assistant", content="b", rich_content=card("form")
        )
        session.add_all([old, other])
        agent = AgentRow(owner_id=owner.id, name="Peer")
        session.add(agent)
        await session.flush()
        # A peer run's result card, which the outcome return reads later.
        run = RunRow(
            thread_id=thread.id,
            agent_id=agent.id,
            status="completed",
            model_metadata={"rich_content": card("receipt"), "kept": "as is"},
        )
        session.add(run)
        await session.flush()
        ids, run_id = [old.id, other.id], run.id
    await db.engine.dispose()
    alembic("upgrade", "head")
    assert await kinds(db, ids) == ["summary", "form"]
    async with db.sessions() as session:
        stored_run = await session.get(RunRow, run_id)
        assert stored_run is not None
        metadata = stored_run.model_metadata
        assert metadata["rich_content"]["parts"][1]["document"]["kind"] == "summary"
        assert metadata["kept"] == "as is"
    async with db.sessions() as session:
        stored = await session.get(MessageRow, ids[0])
        assert stored is not None and stored.rich_content is not None
        RichContent.model_validate(stored.rich_content)
        assert stored.rich_content["parts"][1]["document"]["title"] == "Alert active"
    print("PASS a stored receipt card is a summary card, unchanged otherwise, and still valid")
    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    assert await kinds(db, ids) == ["receipt", "form"]
    await db.engine.dispose()
    alembic("upgrade", "head")
    print("PASS 0102 downgrades and upgrades again cleanly")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
