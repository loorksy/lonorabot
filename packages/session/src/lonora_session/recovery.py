from datetime import datetime

from lonora_db.runs import aware


def lease_expired(expires_at: datetime | None, now: datetime) -> bool:
    return expires_at is not None and aware(expires_at) <= now
