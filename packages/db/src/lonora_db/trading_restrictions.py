"""Durable owner restrictions on financial admission (see lonora_trading.restrictions).

Creation and the execution boundary's final check are serialized per account by a
transaction-scoped advisory lock: the send boundary holds it shared while it decides,
creation holds it exclusively. An operation therefore either committed its send
authorization before a restriction existed (it is reported as already submitted), or
its final check sees the restriction. Expiry needs no scheduler: every read evaluates
``valid_from``/``valid_until`` against the current time.
"""

from datetime import datetime
from typing import Any

from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.trading_restrictions import (
    RestrictionActionClass,
    RestrictionSource,
    RestrictionState,
)
from lonora_core.user_error import LonoraError
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import fixed_market
from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import AgentRow, TradingRestrictionRow
from .transactions import owned_agent


def restriction_lock_key(owner_id: str, account_id: str) -> str:
    return "trading_restrictions:" + owner_id + ":" + account_id


async def restriction_lock(
    session: AsyncSession, owner_id: str, account_id: str, *, shared: bool
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    await session.execute(
        text(f"SELECT {function}(hashtextextended(:key, 0))"),
        {"key": restriction_lock_key(owner_id, account_id)},
    )


def restriction_state(row: TradingRestrictionRow, now: datetime | None = None) -> RestrictionState:
    moment = now or utcnow()
    if row.revoked_at is not None:
        return "revoked"
    if row.valid_until is not None and row.valid_until <= moment:
        return "expired"
    if row.valid_from > moment:
        return "scheduled"
    return "active"


def relevant_to(row: TradingRestrictionRow, agent: AgentRow) -> bool:
    """Whether an agent may see a restriction: a market-bound agent sees its own market only."""
    if not fixed_market(agent):
        return True
    return row.account_id == agent.trading_account_id and (
        row.symbol is None or row.symbol.casefold() == (agent.trading_symbol or "").casefold()
    )


def restriction_data(row: TradingRestrictionRow, now: datetime | None = None) -> dict[str, Any]:
    state = restriction_state(row, now)
    ended_at = (
        row.revoked_at if state == "revoked" else row.valid_until if state == "expired" else None
    )
    return {
        "id": row.id,
        "account_id": row.account_id,
        "agent_id": row.agent_id,
        "all_agents": row.agent_id is None,
        "symbol": row.symbol,
        "all_symbols": row.symbol is None,
        # False: the broker catalog could not be read when it was created, so the symbol
        # is stored as given and matches only that spelling (ignoring case).
        "symbol_verified": row.symbol is None or row.symbol_verified is not False,
        "action_class": row.action_class,
        "state": state,
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "ended_at": ended_at.isoformat() if ended_at else None,
        "applies_to_owner_manual": row.applies_to_owner_manual,
        "source": row.source,
        "source_message_id": row.source_message_id,
        "source_run_id": row.source_run_id,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_by_agent_id": row.created_by_agent_id,
        "created_at": row.created_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoked_reason": row.revoked_reason,
        # Lifting is never available to an agent; only the owner's session can revoke.
        "lift": "owner_only",
    }


async def create_restriction(
    session: AsyncSession,
    owner_id: str,
    *,
    account_id: str,
    action_class: RestrictionActionClass,
    source: RestrictionSource,
    created_by_agent_id: str | None,
    agent_id: str | None = None,
    symbol: str | None = None,
    symbol_verified: bool = True,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    reason: str = "",
    source_message_id: str | None = None,
    source_run_id: str | None = None,
    applies_to_owner_manual: bool = False,
    restriction_id: str | None = None,
) -> TradingRestrictionRow:
    """Persist a restriction; ``restriction_id`` makes a replayed creation idempotent."""
    if restriction_id is not None:
        existing = await session.get(TradingRestrictionRow, restriction_id)
        if existing is not None:
            if existing.owner_id != owner_id:
                raise LonoraError("restriction_not_found", 404)
            return existing
    if (source == "owner_ui") != (created_by_agent_id is None):
        raise LonoraError("restriction_creator_invalid", 409)
    if created_by_agent_id is not None and applies_to_owner_manual:
        # An agent narrows agent activity; only the owner can restrict the owner.
        raise LonoraError("restriction_owner_manual_owner_only", 403)
    if applies_to_owner_manual and agent_id is not None:
        # The owner flag binds the owner's own trades; one agent's scope never does.
        raise LonoraError("restriction_owner_manual_agent_conflict", 422)
    await BrokerSessionRepository().get(session, owner_id, account_id)
    if agent_id is not None:
        await owned_agent(session, owner_id, agent_id)
    now = utcnow()
    start = valid_from or now
    if start.tzinfo is None or (valid_until is not None and valid_until.tzinfo is None):
        raise LonoraError("restriction_time_zone_required", 422)
    if valid_until is not None and valid_until <= max(start, now):
        raise LonoraError("restriction_window_invalid", 422)
    await restriction_lock(session, owner_id, account_id, shared=False)
    row = TradingRestrictionRow(
        id=restriction_id or new_id(),
        owner_id=owner_id,
        account_id=account_id,
        agent_id=agent_id,
        symbol=symbol,
        symbol_verified=symbol is None or symbol_verified,
        action_class=action_class,
        valid_from=start,
        valid_until=valid_until,
        source=source,
        source_message_id=source_message_id,
        source_run_id=source_run_id,
        reason=reason,
        created_by="owner" if created_by_agent_id is None else "agent",
        created_by_agent_id=created_by_agent_id,
        applies_to_owner_manual=applies_to_owner_manual,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    emit(
        session,
        owner_id,
        "trading.restriction_created",
        agent_id=agent_id,
        run_id=source_run_id,
        payload={"restriction": restriction_data(row, now), "transition_id": row.id + ":created"},
    )
    return row


async def revoke_restriction(
    session: AsyncSession, owner_id: str, restriction_id: str, reason: str = ""
) -> TradingRestrictionRow:
    """Owner action only: lifting a restriction re-admits what it prohibited."""
    row = await session.get(TradingRestrictionRow, restriction_id, with_for_update=True)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("restriction_not_found", 404)
    if row.revoked_at is not None:
        return row
    now = utcnow()
    row.revoked_at = row.updated_at = now
    row.revoked_reason = reason.strip() or None
    emit(
        session,
        owner_id,
        "trading.restriction_revoked",
        agent_id=row.agent_id,
        payload={"restriction": restriction_data(row, now), "transition_id": row.id + ":revoked"},
    )
    return row


async def restrictions_in_force(
    session: AsyncSession, owner_id: str, account_id: str, now: datetime | None = None
) -> list[TradingRestrictionRow]:
    """Restrictions on this account in force at ``now`` (for every agent and symbol)."""
    moment = now or utcnow()
    return list(
        await session.scalars(
            select(TradingRestrictionRow)
            .where(
                TradingRestrictionRow.owner_id == owner_id,
                TradingRestrictionRow.account_id == account_id,
                TradingRestrictionRow.revoked_at.is_(None),
                TradingRestrictionRow.valid_from <= moment,
                or_(
                    TradingRestrictionRow.valid_until.is_(None),
                    TradingRestrictionRow.valid_until > moment,
                ),
            )
            .order_by(TradingRestrictionRow.created_at, TradingRestrictionRow.id)
        )
    )


async def list_restrictions(
    session: AsyncSession,
    owner_id: str,
    *,
    account_id: str | None = None,
    agent_id: str | None = None,
    include_ended: bool = False,
    limit: int = 50,
    now: datetime | None = None,
) -> list[TradingRestrictionRow]:
    """Current (active or scheduled) restrictions, newest first; optionally ended ones.

    ``agent_id`` keeps restrictions that apply to that agent: its own and all-agent ones.
    """
    moment = now or utcnow()
    query = select(TradingRestrictionRow).where(TradingRestrictionRow.owner_id == owner_id)
    if account_id is not None:
        query = query.where(TradingRestrictionRow.account_id == account_id)
    if agent_id is not None:
        query = query.where(
            or_(
                TradingRestrictionRow.agent_id.is_(None), TradingRestrictionRow.agent_id == agent_id
            )
        )
    if not include_ended:
        query = query.where(
            TradingRestrictionRow.revoked_at.is_(None),
            or_(
                TradingRestrictionRow.valid_until.is_(None),
                TradingRestrictionRow.valid_until > moment,
            ),
        )
    return list(
        await session.scalars(
            query.order_by(TradingRestrictionRow.created_at.desc(), TradingRestrictionRow.id).limit(
                limit
            )
        )
    )
