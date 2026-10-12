from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScheduledWake:
    routine_id: str
    agent_id: str
    thread_id: str
    scheduled_at: datetime
