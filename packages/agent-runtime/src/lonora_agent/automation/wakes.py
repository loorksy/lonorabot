from typing import Any

from lonora_contracts.runs import RunRequest
from lonora_db.client import Database
from lonora_db.runs import create_run, run_data


async def wake_agent(db: Database, owner_id: str, request: RunRequest) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        return run_data(await create_run(session, owner_id, request))
