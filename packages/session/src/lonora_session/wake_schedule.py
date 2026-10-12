from datetime import datetime


def wake_metadata(trigger: str, source_id: str, scheduled_at: datetime) -> dict[str, str]:
    return {"trigger": trigger, "source_id": source_id, "scheduled_at": scheduled_at.isoformat()}
