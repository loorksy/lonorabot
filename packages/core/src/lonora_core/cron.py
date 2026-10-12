from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from .user_error import LonoraError


def next_occurrence(expression: str, timezone: str, after: datetime) -> datetime:
    if not croniter.is_valid(expression):
        raise LonoraError("invalid_cron")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise LonoraError("invalid_timezone") from None
    return croniter(expression, after.astimezone(zone)).get_next(datetime)
