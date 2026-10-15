"""Real PostgreSQL regression for collaboration lineage, one synthesis, and cancellation."""

import asyncio
from typing import Any, cast

from check_streaming import Fixture
from lonora_agent.collaboration.outcome_return import return_outcome, return_pending_outcomes
from lonora_contracts.domain import MessageCreate
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_db.collaboration import current_session
from lonora_db.messages import send_message
from lonora_db.schema import CollaborationSessionRow, MessageRow, RunRow
from lonora_db.tasks import control_task, create_task
from sqlalchemy import select


async def main() -> None:
    f = await Fixture().open()
    try:
        host = await f.agent("Synthesis host")
        peers = [await f.agent("Participant " + str(i)) for i in range(3)]
        thread = await f.conversation(host)
        async with f.runtime.db.sessions() as session, session.begin():
            request = MessageCreate(
                content="Compare this exact objective", mention_agent_ids=[p["id"] for p in peers]
            )
            sent = await send_message(session, f.owner, thread["id"], request)
            row = await current_session(session, f.owner, thread["id"])
            assert row
            session_id = row.id
            round_id = row.state["rounds"][0]["id"]
            ids = row.state["rounds"][0]["participant_run_ids"]
            parent = await session.get(RunRow, sent["run_ids"][0])
            assert parent
            parent.status = "completed"
            parent.result = "Requested contributions"
            for index, identifier in enumerate(ids):
                run = await session.get(RunRow, identifier)
                assert run
                run.status, run.result = "completed", "Actual evidence " + str(index)
        await asyncio.wait_for(
            asyncio.gather(
                *(return_outcome(f.runtime.db, identifier) for identifier in ids for _ in range(3))
            ),
            20,
        )
        # New service/database sessions reproduce process restart/replayed deliveries.
        await return_pending_outcomes(f.runtime.db)
        async with f.runtime.db.sessions() as session:
            row = await session.get(CollaborationSessionRow, session_id)
            assert row
            synthesis = row.state["rounds"][0]["synthesis_run_id"]
            runs = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.thread_id == thread["id"], RunRow.trigger == "follow_up"
                    )
                )
            )
            assert len(runs) == 1 and runs[0].id == synthesis
            assert runs[0].model_metadata["collaboration_round_id"] == round_id
            assert runs[0].parent_run_id == sent["run_ids"][0]
            guests = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == thread["id"],
                        MessageRow.agent_id.in_([p["id"] for p in peers]),
                    )
                )
            )
            assert len(guests) == 3
            assert all(p["status"] == "completed" for p in row.state["participants"])
        print(
            "PASS three concurrent outcomes and nine duplicate deliveries create exactly one fenced synthesis with complete persisted evidence"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            unrelated = MessageCreate(
                content="A completely different objective", mention_agent_ids=[peers[0]["id"]]
            )
            second = await send_message(session, f.owner, thread["id"], unrelated)
            row = await current_session(session, f.owner, thread["id"])
            assert row and row.id != session_id
            second_id = row.id
            assert len(row.state["participants"]) == 1
            repeated = await send_message(session, f.owner, thread["id"], unrelated)
            assert repeated["deduplicated"]
            first = await session.get(CollaborationSessionRow, session_id)
            assert first and len(first.state["rounds"]) == 1
            continuation = MessageCreate(
                content="Revalidate original evidence",
                mention_all=True,
                collaboration_session_id=session_id,
            )
            again = await send_message(session, f.owner, thread["id"], continuation)
            assert again["message"]["mentions"]["session_id"] == session_id
            first = await session.get(CollaborationSessionRow, session_id)
            assert first and len(first.state["rounds"]) == 2
            assert {p["agent_id"] for p in first.state["participants"]} == {p["id"] for p in peers}
            row = await session.get(CollaborationSessionRow, second_id)
            assert row and len(row.state["rounds"]) == 1
            assert all(len(p["run_ids"]) == 1 for p in row.state["participants"])
            assert second["message"]["id"] != sent["message"]["id"]
        print(
            "PASS unrelated objectives get separate durable sessions; explicit @all continues only its captured session and retry creates no session"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            synth = await session.get(RunRow, synthesis)
            assert synth
            synth.status, synth.result = "completed", "Final synthesis from actual evidence"
        await return_outcome(f.runtime.db, synthesis)
        async with f.runtime.db.sessions() as session:
            count = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.thread_id == thread["id"], RunRow.trigger == "follow_up"
                    )
                )
            )
            assert len(count) == 1
        print("PASS completed synthesis cannot recursively spawn another financial reasoning run")

        async with f.runtime.db.sessions() as session, session.begin():
            ticket = await create_task(
                session, f.owner, host["id"], thread["id"], TaskCreate(title="Cancel persistently")
            )
            task_id, run_id = ticket.id, ticket.payload["run_id"]
            await control_task(
                session,
                f.owner,
                TaskControl(task_id=task_id, action="cancel", expected_version=ticket.version),
            )
        await return_outcome(f.runtime.db, run_id)
        await return_outcome(f.runtime.db, run_id)
        task = await f.request("GET", "/tasks/" + task_id)
        ticket = await f.request("GET", "/tickets/" + task_id)
        assert task["status"] == task["phase"] == ticket["payload"]["status"] == "cancelled"
        assert ticket["state"]["task"]["status"] == "cancelled"
        assert not any(task[key] for key in ("can_resume", "can_pause", "can_cancel"))
        edit = await f.client.put(
            "/api/tickets/" + task_id,
            json={
                "version": ticket["version"],
                "payload": {**ticket["payload"], "status": "failed"},
            },
        )
        assert edit.status_code == 409
        # Stale worker success is not permission to revive owner-cancelled work.
        async with f.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id)
            assert run
            run.status, run.lease_fence = "completed", run.lease_fence + 1
        await return_outcome(f.runtime.db, run_id)
        read = await f.request("GET", "/tasks/" + task_id)
        assert read["status"] == "cancelled"
        projected = await f.request("GET", "/agents/" + host["id"] + "/state")
        assert all(t["id"] != task_id for t in cast(list[dict[str, Any]], projected["tasks"]))
        print(
            "PASS cancelled task stays cancelled in internal payload, API/restart/live state and stale result; generic ticket edits cannot forge failure"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
