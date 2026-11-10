from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import SCHEDULE_FIELDS, RoutineCreate, RoutineUpdate
from lonora_db.client import Database
from lonora_db.routines import create_routine, next_run, owned_routine, routine_data


class RoutineService:
    def __init__(self, db: Database):
        self.db = db

    async def create(self, owner_id: str, agent_id: str, request: RoutineCreate) -> dict[str, Any]:
        async with self.db.sessions() as session, session.begin():
            return routine_data(await create_routine(session, owner_id, agent_id, request))

    async def configure(
        self, owner_id: str, routine_id: str, update: RoutineUpdate | RoutineCreate
    ) -> dict[str, Any]:
        async with self.db.sessions() as session, session.begin():
            row = await owned_routine(session, owner_id, routine_id)
            sent = update.model_dump(include=update.model_fields_set)
            merged = {
                "goal_id": row.goal_id,
                "step_id": row.step_id,
                "title": row.title,
                "prompt": row.prompt,
                "interval_seconds": row.interval_seconds,
                "cron": row.cron,
                "run_at": row.run_at,
                "timezone": row.timezone,
                "enabled": row.enabled,
            }
            if any(field in sent for field in SCHEDULE_FIELDS):
                merged.update(dict.fromkeys(SCHEDULE_FIELDS))
            merged.update({key: value for key, value in sent.items() if value is not None})
            if "title" in sent:
                merged["title"] = sent["title"]
            request = RoutineCreate.model_validate(merged)
            from lonora_db.supervision import owner_takes_over

            # The owner switching the routine on or off wins over a supervisor's pause;
            # saving its schedule with the switch unchanged leaves the pause as it is.
            if request.enabled != row.enabled:
                await owner_takes_over(
                    session,
                    owner_id,
                    "routine",
                    routine_id,
                    paused=not request.enabled,
                    agent_id=row.agent_id,
                )
            if request.run_at != row.run_at:
                # A new one-shot time is a new schedule: it may fire again.
                row.last_run_at = None
            for key, value in request.model_dump().items():
                setattr(row, key, value)
            row.next_run_at = next_run(request, utcnow())
            return routine_data(row)
