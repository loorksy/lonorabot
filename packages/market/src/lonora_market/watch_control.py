from datetime import datetime, timedelta

from lonora_db.runs import aware


def watch_can_trigger(
    enabled: bool, last_triggered: datetime | None, cooldown_seconds: int, now: datetime
) -> bool:
    return enabled and (
        last_triggered is None or now - aware(last_triggered) >= timedelta(seconds=cooldown_seconds)
    )
