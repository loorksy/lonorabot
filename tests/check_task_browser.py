"""Create an actual failed Task attempt for browser recovery acceptance."""

import asyncio
import json
import sys
from datetime import timedelta

from check_streaming import test_settings
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.runs import fail_run
from lonora_db.schema import RunRow
from lonora_db.tasks import get_task


async def main():
    params = json.load(sys.stdin)
    db = Database.connect(test_settings().database_url)
    try:
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, params["run_id"], with_for_update=True)
            assert (
                run
                and run.status == "queued"
                and run.model_metadata.get("task_id") == params["task_id"]
            )
            owner = params["owner_id"]
            task = await get_task(session, owner, params["task_id"])
            assert task.agent_id == run.agent_id
            run.status, run.lease_owner = "running", "browser-task-fixture"
            run.lease_fence += 1
            run.lease_expires_at = utcnow() + timedelta(seconds=120)
            await session.flush()
            await fail_run(
                session,
                Lease(run_id=run.id, owner="browser-task-fixture", fence=run.lease_fence),
                "model_provider_unavailable",
            )
        print(json.dumps({"failed": True}))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
