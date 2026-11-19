"""One bounded, source-timestamp-aware health projection shared by runtime consumers."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import Field

from .domain import Contract

HealthState = Literal["healthy", "degraded", "stale", "unavailable", "recovering"]


class HealthSnapshot(Contract):
    state: HealthState
    reason_code: str
    observed_at: datetime
    last_good_at: datetime | None = None
    account_id: str
    symbol: str | None = None
    timeframe: str | None = None
    resource: Literal["quote", "candles", "account", "broker", "watch"]
    measurements: dict[str, Any] = Field(default_factory=dict[str, Any])

    @property
    def healthy(self) -> bool:
        return self.state == "healthy"


# A stored healthy quote is written only when a quote arrives; when quotes stop, nothing
# writes again. Read as it is now, a healthy quote older than this is stale (0.4).
QUOTE_STALE_AFTER = timedelta(minutes=2)


def as_of(stored: dict[str, Any], now: datetime) -> dict[str, Any]:
    """A stored health entry as it reads at ``now``: a healthy quote not refreshed for
    ``QUOTE_STALE_AFTER`` is ``stale`` (``market_quote_stale``), never ``healthy``."""
    if stored.get("resource") != "quote" or stored.get("state") != "healthy":
        return stored
    try:
        observed = datetime.fromisoformat(str(stored.get("observed_at")))
    except ValueError:
        observed = None
    if observed is not None and observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    if observed is not None and now - observed < QUOTE_STALE_AFTER:
        return stored
    return {**stored, "state": "stale", "reason_code": "market_quote_stale"}
