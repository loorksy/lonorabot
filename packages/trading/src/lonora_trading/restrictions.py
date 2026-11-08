"""Owner restrictions applied at the financial boundary.

A restriction in force (``lonora_db.trading_restrictions``) prohibits, on its account and
optional agent/symbol scope, one action class:

- ``no_new_entries``: market and pending entries and pending-entry edits (``modify_order``).
  Closing, cancelling and managing existing positions stay admissible.
- ``no_risk_increase``: everything that is not risk-reducing against the fresh broker
  target (``admission.risk_reducing``): closes, cancellations and tightening or adding
  a stop-loss stay admissible.
- ``all_mutations``: every broker mutation in the scope, reduce-only included.

Restrictions govern agent-originated operations (every leased path: account grant,
exact approval, Goal step). Owner-manual operations are exempt unless the owner flagged
an all-agent restriction ``applies_to_owner_manual``; a restriction scoped to one agent
never binds the owner (creation rejects the combination, and matching ignores it).
Shadow execution never reaches a broker and is not affected. The final decision is made
inside the executor's before-send callback, under the account send lock and the
restriction lock, so queued work and every admission path are covered; an operation
already sent is never reversed.
"""

from datetime import datetime
from typing import Any

from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingRestrictionRow
from lonora_db.trading_restrictions import (
    database_now,
    restriction_data,
    restrictions_in_force,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS

ENTRY_CLASS = frozenset(ENTRY_ACTIONS | {"modify_order"})


class AdmissionBlocked(LonoraError):
    """A boundary decision with evidence the executor records on the journal row."""

    def __init__(self, code: str, evidence: dict[str, Any], status: int = 409):
        super().__init__(code, status)
        self.evidence = evidence


def prohibits(action_class: str, request: TradeRequest, *, reducing: bool) -> bool:
    if action_class == "all_mutations":
        return True
    if action_class == "no_risk_increase":
        return not reducing
    return request.action in ENTRY_CLASS


def applies(row: TradingRestrictionRow, request: TradeRequest, *, agent_id: str | None) -> bool:
    """Scope match; ``agent_id`` None means an owner-manual operation."""
    if row.account_id != request.account_id:
        return False
    # Case-insensitive symbol match can only over-restrict, never miss the market.
    if row.symbol is not None and row.symbol.casefold() != request.symbol.casefold():
        return False
    if agent_id is None:
        # Only an all-agent restriction the owner flagged binds the owner's own trades.
        return row.agent_id is None and bool(row.applies_to_owner_manual)
    return row.agent_id is None or row.agent_id == agent_id


async def blocking_restriction(
    session: AsyncSession,
    owner_id: str,
    request: TradeRequest,
    *,
    agent_id: str | None,
    reducing: bool,
    now: datetime | None = None,
) -> TradingRestrictionRow | None:
    moment = now or await database_now(session)
    for row in await restrictions_in_force(session, owner_id, request.account_id, moment):
        if applies(row, request, agent_id=agent_id) and prohibits(
            row.action_class, request, reducing=reducing
        ):
            return row
    return None


async def require_unrestricted(
    session: AsyncSession,
    owner_id: str,
    request: TradeRequest,
    *,
    agent_id: str | None,
    reducing: bool,
    now: datetime | None = None,
) -> None:
    moment = now or await database_now(session)
    row = await blocking_restriction(
        session, owner_id, request, agent_id=agent_id, reducing=reducing, now=moment
    )
    if row is not None:
        raise AdmissionBlocked(
            "trading_restriction_active",
            {"code": "trading_restriction_active", "restriction": restriction_data(row, moment)},
        )
