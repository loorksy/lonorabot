from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_db.client import Database
from lonora_db.routines import create_routine, next_run, owned_routine, routine_data


class RoutineService:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, owner_id: str, agent_id: str, request: RoutineCreate) -> dict[str, Any]:
        async with self.db.sessions() as session, session.begin():
            return routine_data(await create_routine(session, owner_id, agent_id, request))

    async def configure(
        self, owner_id: str, routine_id: str, request: RoutineCreate
    ) -> dict[str, Any]:
        async with self.db.sessions() as session, session.begin():
            row = await owned_routine(session, owner_id, routine_id)
            for key, value in request.model_dump().items():
                setattr(row, key, value)
            row.next_run_at = next_run(request, utcnow())
            return routine_data(row)
