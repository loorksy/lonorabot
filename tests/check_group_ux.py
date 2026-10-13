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
                },
            )
            thread = {"id": group["thread_id"]}
            runs = [await fixture.run(agent, thread) for agent in [a, b]]
            contexts = [await fixture.lease(run) for run in runs]
            for context in contexts:
                await progress(context, "run.model", {"provider": "scripted", "model": "fixture"})
            return {
                "agents": [a["id"], b["id"]],
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
