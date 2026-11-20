"""Explicit scripted group status fixtures in a disposable PostgreSQL database."""

import asyncio
import json
import sys
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_agent.progress import progress
from lonora_db.runs import complete_run


async def browser_action(data: dict[str, Any]):
    fixture = await Fixture().open()
    action = data["action"]
    try:
        if action == "init":
            a, b = await fixture.agent("Group lead"), await fixture.agent("Group observer")
            group = await fixture.request(
                "POST",
                "/groups/create",
                {
                    "name": "Group UX regression " + uuid4().hex[:8],
                    "member_ids": [a["id"], b["id"]],
                    "participation": "mentions_or_lead",
                    "lead_agent_id": a["id"],
                },
            )
            thread = {"id": group["thread_id"]}
            # The owner's message names no one, so the group's lead is asked to answer it.
            admission = await fixture.request(
                "POST",
                f"/threads/{thread['id']}/messages",
                {"content": "Explicit scripted group question", "client_nonce": uuid4().hex},
            )
            # A watch the observer set in this chat wakes it here: background work (11.5).
            watch = await fixture.request(
                "POST",
                "/runs",
                {
                    "agent_id": b["id"],
                    "thread_id": thread["id"],
                    "trigger": "watch",
                    "prompt": "Explicit scripted watch wake",
                },
            )
            runs = [*admission["runs"], watch]
            contexts = [await fixture.lease(run) for run in runs]
            for context in contexts:
                await progress(context, "run.model", {"provider": "scripted", "model": "fixture"})
            return {
                "agents": [a["id"], b["id"]],
                "admitted": [run["agent_id"] for run in admission["runs"]],
                "names": [a["name"], b["name"]],
                "group": group["id"],
                "thread": thread["id"],
                "runs": runs,
                "leases": [context.lease.model_dump() for context in contexts],
            }
        if action == "finish":
            for index, lease in enumerate(data["leases"]):
                context = fixture.context({"lease": lease, "run": data["runs"][index]})
                async with fixture.runtime.db.sessions() as session, session.begin():
                    await complete_run(
                        session,
                        context.lease,
                        "GROUP LEAD durable answer" if index == 0 else "",
                        {"reply_outcome": "answered" if index == 0 else "silent"},
                    )
            return {"finished": True}
        if action == "cleanup":
            fixture.agents = data["agents"]
            fixture.groups = [data["group"]]
            fixture.group_threads = [data["thread"]]
            return {"cleaned": True}
        raise ValueError("Unknown group UX fixture action")
    finally:
        await fixture.close(cleanup=action == "cleanup")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(browser_action(json.load(sys.stdin)))))
