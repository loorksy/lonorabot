"""Agent tools for owner restrictions: create (narrowing only) and list. Never lift.

Creating a restriction can only remove admissible actions, so it needs no financial
authority. When the run was started by the owner's message, the restriction records
that message as its source. Revocation is an owner-session action (API), deliberately
absent here.
"""

from typing import Any

from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_contracts.trading_restrictions import AgentRestrictionRequest, RestrictionListQuery
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding
from lonora_db.runs import require_lease
from lonora_db.schema import MessageRow, RunRow, TradingJournalRow
from lonora_db.trading_restrictions import (
    create_restriction,
    list_restrictions,
    relevant_to,
    restriction_data,
)
from lonora_trading.execution_quality import execution_policy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .symbols import canonical_broker_symbol

# Runs started by the owner's own message in a conversation or group.
OWNER_TRIGGERS = frozenset({"user", "group"})


async def owner_message_id(session: AsyncSession, run: RunRow) -> str | None:
    """The owner's latest message this run answers, or None for non-owner wakes."""
    if run.trigger not in OWNER_TRIGGERS:
        return None
    return await session.scalar(
        select(MessageRow.id)
        .where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.role == "user",
            MessageRow.seq <= run.input_seq,
        )
        .order_by(MessageRow.seq.desc())
        .limit(1)
    )


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = AgentRestrictionRequest.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
    account_id = params.account_id or agent.trading_account_id
    if account_id is None:
        raise LonoraError("restriction_account_required", 422)
    symbol = params.symbol
    if symbol is not None:
        try:
            broker = await context.brokers.get(context.owner_id, account_id)
        except Exception:
            broker = None  # Narrowing must never depend on broker availability.
        if broker is not None:
            symbol = await canonical_broker_symbol(broker, symbol)
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        message_id = await owner_message_id(session, run)
        row = await create_restriction(
            session,
            context.owner_id,
            account_id=account_id,
            agent_id=None if params.all_agents else params.agent_id or context.agent_id,
            symbol=symbol,
            action_class=params.action_class,
            valid_from=params.valid_from,
            valid_until=params.valid_until,
            reason=params.reason,
            source="owner_message" if message_id else "agent",
            source_message_id=message_id,
            source_run_id=run.id,
            created_by_agent_id=context.agent_id,
            # A crash-replayed call returns the same restriction instead of a second one.
            restriction_id=context.resource_id,
        )
        query = select(TradingJournalRow).where(
            TradingJournalRow.owner_id == context.owner_id,
            TradingJournalRow.account_id == account_id,
            TradingJournalRow.execution_mode == "live",
            TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
        )
        if row.symbol is not None:
            query = query.where(TradingJournalRow.request["symbol"].as_string() == row.symbol)
        unresolved = list(await session.scalars(query.limit(20)))
        return {
            "restriction": restriction_data(row),
            # Already-sent operations are not reversed; report their broker status separately.
            "unresolved_operations_in_scope": [
                {
                    "operation_id": item.operation_id,
                    "symbol": item.request.get("symbol"),
                    "action": item.request.get("action"),
                    "status": item.status,
                }
                for item in unresolved
            ],
            "existing_positions_and_orders_unchanged": True,
            "lift": "owner_only",
        }


async def list_current(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = RestrictionListQuery.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        rows = [
            row
            for row in await list_restrictions(
                session,
                context.owner_id,
                account_id=params.account_id,
                include_ended=params.include_ended,
                limit=params.limit,
            )
            if relevant_to(row, agent)
        ]
    accounts: set[str] = {row.account_id for row in rows}
    accounts.update(
        value for value in (params.account_id, agent.trading_account_id) if value is not None
    )
    account_ids = sorted(accounts)
    limits: list[dict[str, Any]] = []
    for account_id in account_ids:
        policy = await execution_policy(context.db, context.owner_id, account_id)
        limits.append(
            {
                "account_id": account_id,
                "configured": policy.risk.configured,
                **policy.risk.model_dump(mode="json"),
            }
        )
    return {
        "restrictions": [
            {**restriction_data(row), "applies_to_you": row.agent_id in {None, context.agent_id}}
            for row in rows
        ],
        "monetary_risk_limits": limits,
        "lift": "owner_only",
        "execution_authorized": False,
    }


def tools() -> list[Tool]:
    return [
        Tool(
            "trade_restriction_create",
            "Persist an owner restriction that the execution boundary enforces for every agent "
            "operation in scope, including work already queued: no_new_entries (no new market "
            "or pending entries or pending-entry edits; managing, closing and cancelling stay "
            "allowed), no_risk_increase (only closes, cancellations and tighter stops) or "
            "all_mutations (no broker changes). Scope: account (default your bound account), "
            "optional exact symbol (a market-bound agent's own market by default), yourself by "
            "default, another agent_id or all_agents. Set "
            "valid_until for a time-limited instruction such as 'today' (end of the owner's "
            "day, timezone-aware); omit it only for an open-ended one. It only narrows: watches "
            "and analysis continue, existing positions and pending orders are not changed, and "
            "an already submitted operation is not reversed, so check and report those "
            "separately. Only the owner can lift a restriction.",
            AgentRestrictionRequest,
            create,
            replay_safe=True,
        ),
        Tool(
            "trade_restriction_list",
            "Read current owner restrictions (optionally recently ended ones, with when and "
            "how they ended) and the owner's monetary risk limits per account, including "
            "which limits are not configured. Reading authorizes nothing.",
            RestrictionListQuery,
            list_current,
            True,
        ),
    ]
