"""Each gateway step runs in its own supervised task and keeps its own liveness record.

A step that raises backs off and runs again; it never stops another step. A step whose
iteration hangs past its timeout is cancelled and counted as a failure. The heartbeat
step publishes every record, so readiness reflects what is really running.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_db.item_failures import failure_code

log = logging.getLogger("lonora.gateway")


@dataclass(frozen=True)
class StepSpec:
    name: str
    interval: float
    timeout: float
    # A stalled critical step makes the gateway not ready and reaches the owner.
    critical: bool = True

    @property
    def stall_after(self) -> float:
        # Never shorter than one legitimate iteration (its timeout) plus one interval: a
        # slow broker inside the timeout is a broker problem, not a stalled step.
        return max(120.0, self.interval * 12, self.timeout + self.interval)


@dataclass
class StepLiveness:
    spec: StepSpec
    registered_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    succeeded_at: datetime | None = None
    failures: int = 0
    last_error: str | None = None
    # A worker running a Run is busy, not stalled: the Run's lease covers it.
    busy: bool = False

    def stalled(self, now: datetime) -> bool:
        limit = timedelta(seconds=self.spec.stall_after)
        if self.busy:
            return False
        if self.started_at and now - self.started_at > limit:
            return True
        return now - (self.succeeded_at or self.registered_at) > limit

    def snapshot(self, now: datetime) -> dict[str, Any]:
        return {
            "critical": self.spec.critical,
            "interval": self.spec.interval,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "succeeded_at": self.succeeded_at.isoformat() if self.succeeded_at else None,
            "failures": self.failures,
            "last_error": self.last_error,
            "busy": self.busy,
            "stalled": self.stalled(now),
        }


class Liveness:
    """In-process liveness of every step; the heartbeat step persists a snapshot."""

    def __init__(self) -> None:
        self.steps: dict[str, StepLiveness] = {}

    def register(self, spec: StepSpec) -> StepLiveness:
        record = self.steps.get(spec.name)
        if record is None or record.spec != spec:
            record = StepLiveness(spec)
            self.steps[spec.name] = record
        return record

    def stalled(self, now: datetime | None = None, *, critical_only: bool = True) -> list[str]:
        moment = now or utcnow()
        return sorted(
            name
            for name, record in self.steps.items()
            if (record.spec.critical or not critical_only) and record.stalled(moment)
        )

    def snapshot(self) -> dict[str, Any]:
        now = utcnow()
        return {
            "observed_at": now.isoformat(),
            "ready": not self.stalled(now),
            "steps": {name: record.snapshot(now) for name, record in self.steps.items()},
        }


async def supervise_step(
    spec: StepSpec,
    iteration: Callable[[], Awaitable[object]],
    stop: asyncio.Event,
    liveness: Liveness,
) -> None:
    """Run one step forever: its own interval, timeout, failure backoff and liveness."""
    record = liveness.register(spec)
    while not stop.is_set():
        record.started_at = utcnow()
        try:
            async with asyncio.timeout(spec.timeout):
                await iteration()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            record.failures += 1
            record.last_error = (
                "step_timeout" if isinstance(error, TimeoutError) else failure_code(error)
            )
            log.error(
                "step_failed name=%s code=%s failures=%s",
                spec.name,
                record.last_error,
                record.failures,
            )
        else:
            record.failures, record.last_error = 0, None
            record.succeeded_at = utcnow()
        finally:
            record.completed_at, record.started_at = utcnow(), None
        delay = (
            min(60.0, max(spec.interval, 1.0) * 2 ** min(record.failures, 5))
            if record.failures
            else spec.interval
        )
        try:
            await asyncio.wait_for(stop.wait(), delay)
        except TimeoutError:
            continue
