"""Agent tools for owner restrictions: create (narrowing only) and list. Never lift.

Creating a restriction can only remove admissible actions, so it needs no financial
authority. When the run was started by the owner's message, the restriction records
that message as its source. Revocation is an owner-session action (API), deliberately
absent here.

One narrowing is not left to an agent's own initiative: ``all_mutations`` also blocks
risk-reducing exits (closes, cancellations, tighter stops), so an agent may impose it on
another agent or on all agents only when the run answers the owner's message. On its
own initiative an agent may freeze only itself.
"""

from typing import Any

from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_contracts.trading_restrictions import AgentRestrictionRequest, RestrictionListQuery
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, fixed_market
from lonora_db.runs import require_lease
from lonora_db.schema import MessageRow, RunRow, TradingJournalRow, TradingRestrictionRow
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
from .symbols import restriction_symbol

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
        # A crash-replayed call returns the restriction it already created, unchanged.
        replayed = await session.get(TradingRestrictionRow, context.resource_id) is not None
    account_id = params.account_id or agent.trading_account_id
    if account_id is None:
        raise LonoraError("restriction_account_required", 422)
    if params.all_symbols and fixed_market(agent):
        # A market-bound agent's scope is its own market; every symbol exceeds it.
        raise LonoraError("agent_trading_symbol_mismatch", 409)
    symbol = None if params.all_symbols else params.symbol
    verified = True
    if symbol is not None and not replayed:
        try:
            broker = await context.brokers.get(context.owner_id, account_id)
        except Exception:
            broker = None  # Narrowing must never depend on broker availability.
        symbol, verified = await restriction_symbol(broker, symbol)
    scoped_agent = None if params.all_agents else params.agent_id or context.agent_id
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        message_id = await owner_message_id(session, run)
        if (
            not replayed
            and params.action_class == "all_mutations"
            and scoped_agent != context.agent_id
            and message_id is None
        ):
            # Freezing other agents also blocks their protective exits: the owner asks.
            raise LonoraError("restriction_all_mutations_requires_owner_message", 403)
        row = await create_restriction(
            session,
            context.owner_id,
            account_id=account_id,
            agent_id=scoped_agent,
            symbol=symbol,
            symbol_verified=verified,
            action_class=params.action_class,
            valid_from=params.valid_from,
            valid_until=params.valid_until,
            reason=params.reason,
            source="owner_message" if message_id else "agent",
            source_message_id=message_id,
            source_run_id=run.id,
            created_by_agent_id=context.agent_id,
            restriction_id=context.resource_id,
        )
        query = select(TradingJournalRow).where(
            TradingJournalRow.owner_id == context.owner_id,
            TradingJournalRow.account_id == row.account_id,
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
            "allowed), no_risk_increase (only closes, cancellations of orders that would add "
            "exposure, and tighter stops; closing a hedge leg stays allowed even though it "
            "changes net direction, cancelling a protective opposite-side order does not) or "
            "all_mutations (no broker changes, exits included; for another agent or all "
            "agents only when the owner's message asked). Scope: account (default your bound "
            "account); symbol (the broker must list it; your home market by default on your "
            "home account) or all_symbols for every symbol on the account (not for a "
            "market-bound agent); yourself by default, another agent_id or all_agents. Set "
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
