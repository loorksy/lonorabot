"""One bounded, source-timestamp-aware health projection shared by runtime consumers."""

from datetime import datetime
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
