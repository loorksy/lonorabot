"""Migration 0155: a pause made from the owner's message becomes the owner's (mandate 4.7.2).

On a disposable PostgreSQL at head: step down below 0155, record a live hold with the
old ``owner_message`` source, an agent's own hold, and an ``owner`` hold that still
names the message it began from (the owner then paused it with a control), step up
again. The first is the owner's now (holder and message kept), the second is
unchanged, the third stays control-only (its message id is cleared, so no chat lifts
it), and the CHECK refuses the old source. The downgrade keeps the owner's pause the
owner's, and the upgrade runs again cleanly.
"""

import asyncio
import subprocess
import sys
from uuid import uuid4

from check_trading import database
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_core.user_error import LonoraError
from lonora_db.agents import create_agent
from lonora_db.market_watches import control_watch
from lonora_db.pauses import refuse_held
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import MarketWatchRow, MessageRow, OwnerRow, SupervisionHoldRow
from lonora_db.threads import conversation_thread
from sqlalchemy import delete, select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0173_reach_me_without_activity"


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
        # Production's shape: the owner cancelled three of Lonora's watches, each an
        # unreleased owner hold (source owner, no holder) on a watch of the personal agent.
        lonora = await ensure_personal_agent(session, owner_id)
        thread = await conversation_thread(session, owner_id, lonora.id)
        watch_ids: list[str] = []
        for level in ("1.0800", "1.0850", "1.0900"):
            watch = MarketWatchRow(
                owner_id=owner_id,
                agent_id=lonora.id,
                thread_id=thread.id,
                payload={
                    "kind": "price",
                    "symbol": "EURUSDm",
                    "condition": "above",
                    "level": level,
                    "prompt": "EURUSDm level",
                    "enabled": True,
                },
                state={},
            )
            session.add(watch)
            await session.flush()
            await control_watch(session, owner_id, watch.id, "cancel")
            watch_ids.append(watch.id)
        lonora_id = lonora.id
        # The owner's words a chat pause names (``source_message_id``).
        words = MessageRow(thread_id=thread.id, seq=thread.next_seq, role="user", content="x")
        thread.next_seq += 1
        session.add(words)
        await session.flush()
        words_id = words.id

    async def owner_holds() -> dict[str, str]:
        """Each owner hold on those watches, as the update's control fingerprint hashes it."""
        async with db.sessions() as session:
            rows = await session.execute(
                text(
                    "SELECT t.target_id, md5(t::text) FROM ln_supervision_holds t"
                    " WHERE t.target_kind = 'watch' AND t.target_id = ANY(:ids)"
                ),
                {"ids": watch_ids},
            )
            return {target: digest for target, digest in rows.all()}

    kept = await owner_holds()
    assert len(kept) == 3, kept
    async with db.sessions() as session:
        for watch_id in watch_ids:
            hold = await session.scalar(
                select(SupervisionHoldRow).where(SupervisionHoldRow.target_id == watch_id)
            )
            assert hold is not None and hold.agent_id == lonora_id
            assert hold.source == "owner" and hold.holder_agent_id is None
            assert hold.released_at is None
    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    assert await owner_holds() == kept
    asked, own, taken = str(uuid4()), str(uuid4()), str(uuid4())
    async with db.sessions() as session, session.begin():
        for identifier, kind, source, message in (
            (asked, "agent", "owner_message", words_id),
            (own, "task", "agent", None),
            # A chat pause the owner then paused or cancelled with a control: before 0155
            # it was 'owner', control-only, and still named its message.
            (taken, "routine", "owner", words_id),
        ):
            await session.execute(
                text(
                    "INSERT INTO ln_supervision_holds (id, owner_id, holder_agent_id, agent_id,"
                    " target_kind, target_id, source, source_message_id, created_at) VALUES"
                    " (:id, :owner, :holder, :agent, :kind, :target, :source, :message, :at)"
                ),
                {
                    "id": identifier,
                    "owner": owner_id,
                    "holder": holder_id,
                    "agent": paused_id,
                    "kind": kind,
                    "target": paused_id if kind == "agent" else str(uuid4()),
                    "source": source,
                    "message": message,
                    "at": utcnow(),
                },
            )
    await db.engine.dispose()
    alembic("upgrade", "head")
    assert await owner_holds() == kept
    async with db.sessions() as session:
        rows = {
            row.id: row
            for row in await session.scalars(
                select(SupervisionHoldRow).where(SupervisionHoldRow.id.in_([asked, own, taken]))
            )
        }
        assert rows[asked].source == "owner" and rows[asked].holder_agent_id == holder_id
        # Asked for in chat: the owner lifts it by asking in chat again.
        assert rows[asked].source_message_id == words_id
        assert rows[own].source == "agent"
        # The owner's control made it control-only: no chat lifts it after the upgrade.
        assert rows[taken].source == "owner" and rows[taken].source_message_id is None
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
    assert await owner_holds() == kept
    await db.engine.dispose()
    alembic("upgrade", "head")
    # Byte for byte after every step, and still the owner's: Lonora cannot lift them,
    # even from the owner's words; only the owner's own resume does.
    assert await owner_holds() == kept
    for watch_id in watch_ids:
        try:
            async with db.sessions() as session, session.begin():
                await refuse_held(
                    session, owner_id, "watch", watch_id, lonora_id, owner_message=True
                )
        except LonoraError as error:
            assert error.code == "work_paused_by_owner", error.code
        else:
            raise AssertionError("Lonora lifted the owner's pause on its watch")
    async with db.sessions() as session, session.begin():
        await session.execute(
            delete(SupervisionHoldRow).where(SupervisionHoldRow.id.in_([asked, own, taken]))
        )
        await session.execute(delete(MessageRow).where(MessageRow.id == words_id))
        await session.execute(
            delete(SupervisionHoldRow).where(SupervisionHoldRow.target_id.in_(watch_ids))
        )
        await session.execute(delete(MarketWatchRow).where(MarketWatchRow.id.in_(watch_ids)))
    await db.engine.dispose()
    print(
        "PASS 0155: owner_message holds are the owner's; an owner hold its control took over "
        "stays control-only; the owner's holds on Lonora's watches stay byte for byte through "
        "upgrade and downgrade; no pause is weakened"
    )


if __name__ == "__main__":
    asyncio.run(main())
