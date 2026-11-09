"""Per-item fault isolation for the gateway's maintenance steps.

A routine, watch, attention event or integration that raises, or hangs past its own
time limit, is recorded here, backs off and, after repeated failures, is quarantined with
one owner-visible attention item.
Every other item in the batch keeps running. Items tied to an unresolved financial
operation are never quarantined: they only back off, because they must be reconciled.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import ColumnElement, delete, exists, or_, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from .client import Database
from .schema import ItemFailureRow

QUARANTINE_AFTER = 5
# One item's own time limit, well below every step's iteration timeout: an item that
# hangs is recorded as a failure ("timeout") like one that raises, instead of being cut
# off silently by the step timeout and selected first again on every pass.
ITEM_TIMEOUT_SECONDS = 45.0
BACKOFF_SECONDS = 10
MAXIMUM_BACKOFF_SECONDS = 600

log = logging.getLogger("lonora.gateway")

# Makes the quarantined item inert in its own records (for example a disabled routine) in
# the given transaction. True removes the ledger row, so re-enabling starts fresh; False
# keeps the ledger quarantine as the item's only guard.
QuarantineAction = Callable[[AsyncSession, str], Awaitable[bool]]


def failure_code(error: BaseException) -> str:
    """A stable, secret-free code: never the exception message."""
    if isinstance(error, LonoraError):
        return error.code[:120]
    if isinstance(error, TimeoutError):
        return "timeout"
    return ("unexpected_" + re.sub(r"(?<!^)(?=[A-Z])", "_", type(error).__name__).lower())[:120]


def backoff(failures: int) -> timedelta:
    return timedelta(seconds=min(MAXIMUM_BACKOFF_SECONDS, BACKOFF_SECONDS * 2 ** (failures - 1)))


def blocked(kind: str, item_id: Any) -> ColumnElement[bool]:
    """SQL predicate: the item is backing off or quarantined, so a batch skips it.

    Skipped in SQL, a failing item never occupies the batch limit of healthy ones.
    """
    return exists(
        select(ItemFailureRow.item_id).where(
            ItemFailureRow.kind == kind,
            ItemFailureRow.item_id == item_id,
            or_(
                ItemFailureRow.quarantined_at.is_not(None),
                ItemFailureRow.next_attempt_at > utcnow(),
            ),
        )
    )


async def due_retries(
    session: AsyncSession, kind: str, owner_id: str | None, limit: int = 20
) -> list[ItemFailureRow]:
    """Failed items whose backoff has passed, oldest attempt first."""
    query = select(ItemFailureRow).where(
        ItemFailureRow.kind == kind,
        ItemFailureRow.quarantined_at.is_(None),
        ItemFailureRow.next_attempt_at <= utcnow(),
    )
    if owner_id:
        query = query.where(ItemFailureRow.owner_id == owner_id)
    return list(await session.scalars(query.order_by(ItemFailureRow.next_attempt_at).limit(limit)))


class ItemGuard:
    """Runs one batch's items in isolation and keeps their failure records."""

    def __init__(
        self,
        db: Database,
        kind: str,
        *,
        quarantine_after: int | None = QUARANTINE_AFTER,
        quarantine: QuarantineAction | None = None,
        notify_when_inert: bool = True,
        timeout: float | None = None,
    ) -> None:
        self.db, self.kind = db, kind
        # None means the shared item limit; every item has one.
        self.timeout = ITEM_TIMEOUT_SECONDS if timeout is None else timeout
        self.quarantine_after, self.quarantine = quarantine_after, quarantine
        # False when the quarantine action itself reaches the owner (a failed Task).
        self.notify_when_inert = notify_when_inert
        self.failing: set[str] = set()
        self.errors = 0

    async def prepare(self, item_ids: Iterable[str]) -> None:
        """Remember which items have a failure record, so success clears only those."""
        identifiers = sorted(set(item_ids))
        if not identifiers:
            self.failing = set()
            return
        async with self.db.sessions() as session:
            self.failing = set(
                await session.scalars(
                    select(ItemFailureRow.item_id).where(
                        ItemFailureRow.kind == self.kind,
                        ItemFailureRow.item_id.in_(identifiers),
                    )
                )
            )

    async def run[T](
        self, item_id: str, owner_id: str | None, action: Callable[[], Awaitable[T]]
    ) -> T | None:
        try:
            async with asyncio.timeout(self.timeout):
                result = await action()
        except Exception as error:
            self.errors += 1
            await self.fail(item_id, owner_id, error)
            return None
        if item_id in self.failing:
            async with self.db.sessions() as session, session.begin():
                await session.execute(
                    delete(ItemFailureRow).where(
                        ItemFailureRow.kind == self.kind, ItemFailureRow.item_id == item_id
                    )
                )
            self.failing.discard(item_id)
        return result

    async def fail(self, item_id: str, owner_id: str | None, error: BaseException) -> bool:
        """Record one failure; returns True when this failure quarantined the item."""
        code = failure_code(error)
        log.warning("maintenance_item_failed kind=%s code=%s", self.kind, code)
        now = utcnow()
        async with self.db.sessions() as session, session.begin():
            # INSERT arbitrates a first failure seen by two gateways at once (a rolling
            # restart overlap); locking a missing row does not, and a duplicate insert
            # would escape ``run``, which never raises for an item.
            dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
            await session.execute(
                dialect.insert(ItemFailureRow)
                .values(
                    kind=self.kind,
                    item_id=item_id,
                    owner_id=owner_id,
                    failures=0,
                    code=code,
                    first_failed_at=now,
                    last_failed_at=now,
                    next_attempt_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[ItemFailureRow.kind, ItemFailureRow.item_id]
                )
            )
            row = await session.get(
                ItemFailureRow,
                (self.kind, item_id),
                with_for_update=True,
                populate_existing=True,
            )
            assert row is not None
            row.failures += 1
            row.code, row.last_failed_at = code, now
            row.next_attempt_at = now + backoff(row.failures)
            quarantined = (
                self.quarantine_after is not None
                and row.failures >= self.quarantine_after
                and row.quarantined_at is None
            )
            if quarantined:
                row.quarantined_at = now
        self.failing.add(item_id)
        if quarantined:
            await self.quarantined(item_id, row.owner_id, code, now)
        return quarantined

    async def quarantined(
        self, item_id: str, owner_id: str | None, code: str, at: datetime
    ) -> None:
        log.error("maintenance_item_quarantined kind=%s code=%s", self.kind, code)
        inert = False
        if self.quarantine:
            try:
                async with self.db.sessions() as session, session.begin():
                    made_inert = await self.quarantine(session, item_id)
                    if made_inert:
                        await session.execute(
                            delete(ItemFailureRow).where(
                                ItemFailureRow.kind == self.kind,
                                ItemFailureRow.item_id == item_id,
                            )
                        )
                inert = made_inert
            except Exception as error:
                # The ledger quarantine still keeps the item out of every batch.
                log.error(
                    "maintenance_quarantine_action_failed kind=%s code=%s",
                    self.kind,
                    failure_code(error),
                )
        if inert:
            self.failing.discard(item_id)
        if owner_id and (self.notify_when_inert or not inert):
            from .attention import raise_system_attention

            async with self.db.sessions() as session, session.begin():
                await raise_system_attention(
                    session,
                    owner_id,
                    "maintenance_item_quarantined",
                    # A re-enabled item that fails again is a new quarantine.
                    self.kind + ":" + item_id + ":" + at.isoformat(timespec="seconds"),
                    {"item_kind": self.kind, "reason_code": code},
                    # One open notice per kind: a systematic fault adds to its count
                    # instead of flooding the inbox with identical items.
                    group=self.kind,
                )
