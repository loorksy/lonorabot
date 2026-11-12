"""Deleting an agent, conversation or broker connection never erases money history.

The records themselves survive the delete (see migration 0036). Before the delete,
authority and work that depended on the deleted parent are settled explicitly: open
approvals cancelled, grants revoked, Super Bot requests stopped and waiting owner action
cards superseded. Narrowing never needs the owner's passkey, and nothing is left
looking active while it can no longer run. A delete is refused while an operation it
touches still has no confirmed broker outcome, because that obligation must be settled,
not forgotten.
"""

from typing import Any

from lonora_contracts.trading import IN_PROGRESS_STATUSES, UNRESOLVED_STATUSES
from lonora_core.user_error import LonoraError
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    AccountAuthorityRow,
    RunRow,
    TradeApprovalRow,
    TradingJournalRow,
)

UNSETTLED = sorted(IN_PROGRESS_STATUSES | UNRESOLVED_STATUSES)


def attributed_to_runs(runs: Any) -> ColumnElement[bool]:
    details = TradingJournalRow.result["details"]
    return or_(
        details["execution"]["run_id"].as_string().in_(runs),
        details["lease"]["run_id"].as_string().in_(runs),
    )


async def unsettled_obligation(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
) -> bool:
    """A journaled operation in the scope has no confirmed broker outcome yet.

    An approved request that has not reached the journal has no money effect yet; it is
    cancelled (narrowed) by ``prepare_delete`` instead of blocking the delete.
    """
    query = select(TradingJournalRow.operation_id).where(
        TradingJournalRow.owner_id == owner_id,
        TradingJournalRow.status.in_(UNSETTLED),
    )
    if account_id is not None:
        query = query.where(TradingJournalRow.account_id == account_id)
    if agent_id is not None:
        query = query.where(
            or_(
                TradingJournalRow.result["details"]["execution"]["agent_id"].as_string()
                == agent_id,
                attributed_to_runs(select(RunRow.id).where(RunRow.agent_id == agent_id)),
            )
        )
    if thread_id is not None:
        query = query.where(
            attributed_to_runs(select(RunRow.id).where(RunRow.thread_id == thread_id))
        )
    return await session.scalar(query.limit(1)) is not None


async def approvals(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None,
    thread_id: str | None,
    account_id: str | None,
) -> list[TradeApprovalRow]:
    query = select(TradeApprovalRow).where(
        TradeApprovalRow.owner_id == owner_id,
        TradeApprovalRow.status.in_(["pending", "approved"]),
    )
    if agent_id is not None:
        query = query.where(TradeApprovalRow.agent_id == agent_id)
    if thread_id is not None:
        query = query.where(TradeApprovalRow.thread_id == thread_id)
    rows = list(await session.scalars(query.with_for_update()))
    if account_id is None:
        return rows
    return [
        row
        for row in rows
        if any(request.get("account_id") == account_id for request in row.requests)
    ]


async def prepare_delete(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Refuse while an obligation is unsettled; otherwise settle what depended on it."""
    from .account_authority import changed, revoke
    from .owner_actions import settle_for_delete
    from .trade_approvals import approval_event

    if await unsettled_obligation(
        session, owner_id, agent_id=agent_id, thread_id=thread_id, account_id=account_id
    ):
        raise LonoraError("delete_blocked_unresolved_operation", 409)
    # Owner action cards it raised, shown in it or about it no longer apply.
    await settle_for_delete(
        session, owner_id, agent_id=agent_id, thread_id=thread_id, account_id=account_id
    )
    for approval in await approvals(
        session, owner_id, agent_id=agent_id, thread_id=thread_id, account_id=account_id
    ):
        approval.status = "cancelled"
        approval_event(session, approval)
    # A grant signed in a deleted conversation is revoked visibly (the permission frame
    # shows "autonomous stopped"), never left active but unusable.
    grants = select(AccountAuthorityRow).where(
        AccountAuthorityRow.owner_id == owner_id,
        AccountAuthorityRow.status.in_(["pending", "active"]),
    )
    if agent_id is not None:
        grants = grants.where(AccountAuthorityRow.agent_id == agent_id)
    if thread_id is not None:
        grants = grants.where(AccountAuthorityRow.thread_id == thread_id)
    if account_id is not None:
        grants = grants.where(AccountAuthorityRow.account_id == account_id)
    for grant in list(await session.scalars(grants.order_by(AccountAuthorityRow.id))):
        if grant.status == "active":
            await revoke(session, owner_id, grant.id)
        else:
            grant.status = "revoked"
            changed(session, grant)
