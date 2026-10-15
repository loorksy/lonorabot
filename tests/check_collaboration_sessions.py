"""Disposable PostgreSQL: stable mentions route real peer outcomes, not impersonation."""

import asyncio

from check_streaming import Fixture
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_contracts.domain import AgentUpdate, MessageCreate
from lonora_db.agents import update_agent
from lonora_db.collaboration import current_session
from lonora_db.messages import send_message
from lonora_db.schema import CollaborationSessionRow, RunRow


async def main():
    fixture = await Fixture().open()
    try:
        host = await fixture.agent("Host")
        first = await fixture.agent("EUR analyst")
        second = await fixture.agent("Metal analyst")
        thread = await fixture.conversation(host)
        async with fixture.runtime.db.sessions() as session, session.begin():
            request = MessageCreate(
                content="Compare evidence",
                client_nonce="session-mention-check",
                mention_agent_ids=[first["id"], second["id"], first["id"]],
            )
            sent = await send_message(session, fixture.owner, thread["id"], request)
            row = await current_session(session, fixture.owner, thread["id"])
            assert row is not None
            session_id = row.id
            assert len(row.state["participants"]) == 2
            run_ids = [p["run_ids"][0] for p in row.state["participants"]]
            assert sent["message"]["mentions"]["agent_ids"] == [first["id"], second["id"]]
            again = await send_message(session, fixture.owner, thread["id"], request)
            assert again["deduplicated"]
            await update_agent(
                session, fixture.owner, first["id"], AgentUpdate(name="Renamed analyst")
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            for index, identifier in enumerate(run_ids):
                run = await session.get(RunRow, identifier)
                assert run and run.thread_id != thread["id"]
                assert run.parent_run_id == sent["run_ids"][0]
                run.status = "completed" if index == 0 else "failed"
                run.result = "Actual peer evidence" if index == 0 else ""
                run.error_code = "source_unavailable" if index else None
        for identifier in run_ids:
            await return_outcome(fixture.runtime.db, identifier)
            await return_outcome(fixture.runtime.db, identifier)
        messages = (await fixture.client.get(f"/api/threads/{thread['id']}/messages")).json()
        guest = [m for m in messages if m["agent_id"] == first["id"]]
        assert len(guest) == 1 and "Actual peer evidence" in guest[0]["content"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(CollaborationSessionRow, session_id)
            assert row and row.state["status"] == "synthesizing"
            assert row.state["participants"][0]["source_message_id"] == guest[0]["id"]
            assert row.state["participants"][1]["result"] == ""
            all_message = await send_message(
                session,
                fixture.owner,
                thread["id"],
                MessageCreate(content="Recheck", mention_all=True),
            )
            assert all_message["message"]["mentions"]["all"]
            row = await current_session(session, fixture.owner, thread["id"])
            assert row and len(row.state["participants"]) == 2
            assert all(len(p["run_ids"]) == 2 for p in row.state["participants"])
        print(
            "Collaboration: stable rename-safe mentions, multi-peer routing, replay deduplication, actual guest provenance, explicit failure and session-only @all passed"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
