from datetime import datetime

from lonora_contracts.routines import RoutineCreate
from lonora_db.routines import next_run


def compute_next(request: RoutineCreate, after: datetime) -> datetime:
    return next_run(request, after)
