"""A message acknowledgement contains its actual activity without a second GET."""

import pytest
from lonora_contracts.domain import MessageCreate
from lonora_db.client import Database
from lonora_db.messages import history, send_message
from lonora_db.runs import claim_next
from lonora_db.schema import EventRow, RunRow
from sqlalchemy import select
from test_task_runtime import task_db as task_db


@pytest.mark.asyncio
async def test_ack_and_nonce_retry_reuse_canonical_message_and_current_run(
    task_db: tuple[Database, str, str, str],
):
    db, owner, _, thread = task_db
    body = MessageCreate(content="Hello", client_nonce="stable-sending-intent")
    async with db.sessions() as session, session.begin():
        first = await send_message(session, owner, thread, body)
        assert not first["deduplicated"] and len(first["runs"]) == 1
        queued = first["runs"][0]
        assert queued["id"] == first["run_ids"][0] and queued["status"] == "queued"
        assert queued["input_seq"] == first["message"]["seq"]
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, "ack-check", 120, "conversation")
        assert claimed and claimed.id == queued["id"]
    async with db.sessions() as session, session.begin():
        retried = await send_message(session, owner, thread, body)
        assert retried["deduplicated"]
        assert retried["message"]["id"] == first["message"]["id"]
        assert retried["run_ids"] == first["run_ids"]
        assert retried["runs"][0]["status"] == "leased"
        assert len(await history(session, owner, thread)) == 1
        assert len(list(await session.scalars(select(RunRow)))) == 1
        events = list(await session.scalars(select(EventRow).order_by(EventRow.cursor)))
        admitted = next(row for row in events if row.kind == "run.queued")
        leased = next(row for row in events if row.kind == "run.leased")
        assert admitted.payload["run"]["id"] == queued["id"]
        assert admitted.payload["run"]["status"] == "queued"
        assert leased.payload["run"]["status"] == "leased"
