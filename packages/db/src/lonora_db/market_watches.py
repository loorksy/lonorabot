from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.market_watch import Watch
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import IntegrationRow, MarketWatchRow, TicketRow
from .threads import create_thread
from .transactions import ResourceRepository, ResourceRow, owned_agent


class MarketWatchRepository(ResourceRepository):
    row_type = MarketWatchRow
    kind = "market_watches"
    payload_model = Watch

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("integration_id"):
            source = await session.get(IntegrationRow, payload["integration_id"])
            if (
                source is None
                or source.owner_id != owner_id
                or source.payload.get("type") != "economic_calendar"
            ):
                raise LonoraError("calendar_integration_not_found", 404)

    async def stored_payload(
        self, session: AsyncSession, owner_id: str, agent_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """The payload as it is stored: the focus symbol filled.

        Re-arming a watch compares this, so a repeated identical request matches.
        """
        agent = await owned_agent(session, owner_id, agent_id)
        if (
            agent.trading_symbol
            and not payload.get("symbol")
            and payload.get("account_id", agent.trading_account_id) == agent.trading_account_id
        ):
            payload = {**payload, "symbol": agent.trading_symbol}
        return self.validate(payload)

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        if not agent_id:
            raise LonoraError("watch_agent_required", 422)
        payload = await self.stored_payload(session, owner_id, agent_id, payload)
        if not thread_id:
            thread = await create_thread(
                session,
                owner_id,
                ThreadCreate(
                    agent_id=agent_id,
                    title=str(payload.get("prompt", ""))[:80],
                ),
            )
            thread_id = thread.id
        return await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )


WatchAction = Literal["cancel", "pause", "resume"]
# Why a watch is off: the owner's or the agent's own choice, never a failure.
STOP_CODES = {"cancel": "watch_cancelled", "pause": "watch_paused"}


def stop_watch(row: MarketWatchRow, code: str) -> None:
    """Switch a watch off and record why. Its evaluation fields go with it: a stored
    ``evaluation_status: active`` or a coming ``next_check`` reads as a live watch."""
    state = {
        key: value
        for key, value in row.state.items()
        if key not in {"evaluation_status", "next_check"}
    }
    row.payload = {**row.payload, "enabled": False}
    row.state = {**state, "code": code}


def watch_active(row: MarketWatchRow, now: datetime | None = None) -> bool:
    """Enabled, not expired and not past its expiry: it is watching right now."""
    if not row.payload.get("enabled", True) or row.state.get("lifecycle") == "expired":
        return False
    expires = row.payload.get("expires_at")
    return not expires or datetime.fromisoformat(str(expires)) > (now or utcnow())


async def watch_past_expiry(session: AsyncSession, watch_id: str) -> bool:
    """Whether a resume would be refused because the watch is past its expiry."""
    row = await session.get(MarketWatchRow, watch_id)
    expires = row.payload.get("expires_at") if row else None
    return bool(expires) and datetime.fromisoformat(str(expires)) <= utcnow()


async def steered_watch(
    session: AsyncSession, owner_id: str, watch_id: str, agent_id: str | None
) -> MarketWatchRow:
    """The owner's watch, locked; with ``agent_id`` only that agent's own watch.

    Another agent's watch reads as not found, so an agent can neither steer nor probe it.
    """
    row = await session.get(MarketWatchRow, watch_id, with_for_update=True, populate_existing=True)
    if row is None or row.owner_id != owner_id or (agent_id and row.agent_id != agent_id):
        raise LonoraError("market_watches_not_found", 404)
    return row


def _changed(session: AsyncSession, row: MarketWatchRow, by: str) -> None:
    row.version += 1
    row.updated_at = utcnow()
    row.state = {**row.state, "steered_by": by, "steered_at": row.updated_at.isoformat()}
    emit(
        session,
        row.owner_id,
        "market_watches.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload={"id": row.id, "version": row.version},
    )


async def control_watch(
    session: AsyncSession,
    owner_id: str,
    watch_id: str,
    action: WatchAction,
    *,
    agent_id: str | None = None,
    owner_message: bool = False,
) -> MarketWatchRow:
    """Cancel, pause or resume a watch; repeating the same action changes nothing.

    A cancelled or paused watch keeps its record, so resuming it undoes the cancel. A
    watch past its expiry resumes only after its expiry is moved (``update_watch``).
    The agent never resumes a watch a supervisor or the owner holds paused on its own
    initiative (``owner_message``: its run answers the owner's message); it may still
    cancel it, which only narrows and keeps the hold.
    """
    from .pauses import owner_takes_over, refuse_held

    row = await steered_watch(session, owner_id, watch_id, agent_id)
    by = "agent" if agent_id else "owner"
    if agent_id is None:
        # The owner's choice wins over a supervisor's pause of this watch.
        await owner_takes_over(
            session, owner_id, "watch", watch_id, paused=action != "resume", agent_id=row.agent_id
        )
    elif action == "resume":
        await refuse_held(
            session, owner_id, "watch", watch_id, agent_id, owner_message=owner_message
        )
    if action in STOP_CODES:
        code = STOP_CODES[action]
        if not row.payload.get("enabled", True) and row.state.get("code") == code:
            return row
        stop_watch(row, code)
        _changed(session, row, by)
        return row
    if watch_active(row):
        return row
    expires = row.payload.get("expires_at")
    if expires and datetime.fromisoformat(str(expires)) <= utcnow():
        raise LonoraError("watch_expired", 409)
    task = await session.get(TicketRow, row.state.get("task_id") or "")
    if task is not None and task_ended(task):
        # It could only poll: its Task is over, so it would stop itself when it fired.
        raise LonoraError("watch_task_ended", 409)
    state = {key: value for key, value in row.state.items() if key != "code"}
    if state.get("lifecycle") == "expired":
        state["lifecycle"] = "pending"
        state.pop("lifecycle_reason", None)
    row.payload = {**row.payload, "enabled": True}
    row.state = state
    _changed(session, row, by)
    return row


def task_ended(task: TicketRow) -> bool:
    """Cancelled or completed, or the owner asked for either while a worker holds the Run."""
    state: dict[str, Any] = task.state.get("task", {})
    return state.get("status") in {"cancelled", "completed"} or state.get("control_requested") in {
        "cancel",
        "complete",
    }


async def settle_task_watches(session: AsyncSession, task: TicketRow) -> None:
    """Stop the watches a Task's Runs created once the Task is cancelled or completed.

    The owner's request counts from the moment it is made, also while a worker still
    holds the Run: a watch can wake an Agent that holds a signed mandate, so a Task the
    owner ended leaves no trigger behind. A watch already paused or cancelled is settled
    too, so it cannot be resumed into a Task that is over (``control_watch``). A paused
    or failed Task keeps its watches (it resumes); another Task's and the conversation's
    watches are not this Task's.
    """
    if not task_ended(task):
        return
    for row in await session.scalars(
        select(MarketWatchRow)
        .where(
            MarketWatchRow.owner_id == task.owner_id,
            MarketWatchRow.state["task_id"].as_string() == task.id,
        )
        .order_by(MarketWatchRow.id)
        .with_for_update()
    ):
        if row.payload.get("enabled", True) or row.state.get("code") != "task_terminal":
            stop_watch(row, "task_terminal")
            _changed(session, row, "task")


async def update_watch(
    session: AsyncSession,
    owner_id: str,
    watch_id: str,
    *,
    agent_id: str | None = None,
    expires_at: datetime | None = None,
    clear_expiry: bool = False,
    level: Decimal | None = None,
) -> MarketWatchRow:
    """Move a watch's expiry or level; the condition, market and prompt stay as they are.

    An expired watch given a later expiry watches again.
    """
    row = await steered_watch(session, owner_id, watch_id, agent_id)
    payload = dict(row.payload)
    if clear_expiry:
        payload["expires_at"] = None
    elif expires_at is not None:
        if expires_at <= utcnow():
            raise LonoraError("watch_expiry_in_past", 422)
        payload["expires_at"] = expires_at.isoformat()
    if level is not None:
        payload["level"] = str(level)
    try:
        validated = MarketWatchRepository().validate(payload)
    except ValidationError as error:
        raise LonoraError("watch_update_invalid", 422) from error
    if validated == row.payload:
        return row
    state = dict(row.state)
    if state.get("lifecycle") == "expired" and (clear_expiry or expires_at is not None):
        state["lifecycle"] = "pending"
        state.pop("lifecycle_reason", None)
    row.payload, row.state = validated, state
    _changed(session, row, "agent" if agent_id else "owner")
    return row


async def extend_watch(
    session: AsyncSession, owner_id: str, watch_id: str, hours: int
) -> MarketWatchRow:
    """The owner's «تمديد»: the expiry moves ``hours`` later (from now, when it already
    passed, so it watches again). A watch with no expiry has nothing to extend."""
    row = await steered_watch(session, owner_id, watch_id, None)
    expires = row.payload.get("expires_at")
    if not expires:
        raise LonoraError("watch_has_no_expiry", 409)
    base = max(datetime.fromisoformat(str(expires)), utcnow())
    return await update_watch(session, owner_id, watch_id, expires_at=base + timedelta(hours=hours))


async def restore_expiry(
    session: AsyncSession, owner_id: str, watch_id: str, expires_at: str | None, revision: int
) -> MarketWatchRow:
    """Undo of an agent's extension: the earlier expiry back, only while the watch is
    still at the revision that change left (``watch_changed_again`` otherwise). An
    earlier expiry already past leaves the watch expired, as it would have been."""
    row = await steered_watch(session, owner_id, watch_id, None)
    if row.version != revision:
        raise LonoraError("watch_changed_again", 409)
    try:
        row.payload = MarketWatchRepository().validate({**row.payload, "expires_at": expires_at})
    except ValidationError as error:
        raise LonoraError("watch_update_invalid", 422) from error
    _changed(session, row, "owner")
    return row
