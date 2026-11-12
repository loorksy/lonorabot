"""Agent tools for owner restrictions: create (narrowing only) and list. Never lift.

Creating a restriction can only remove admissible actions, so it needs no financial
authority. When the run was started by the owner's message, the restriction records
that message as its source. Revocation is an owner-session action (API), deliberately
absent here.

Narrowing another agent needs a run that answers the owner's message, or a supervision
grant over that agent (over every agent, for all agents; ``lonora_db.supervision``), and
passes the cycle rule: an agent never narrows one that holds an active pause over it
unless the owner asks. ``all_mutations`` on another agent or on all agents always needs
the owner's message: on its own initiative an agent may freeze only itself. Whatever its class, a restriction an agent
records never blocks a risk-reducing exit (``lonora_trading.restrictions``): its scope
and reason are model-authored and may come from injected content.

A restriction an agent records for another agent or for all agents is time-boxed: it
needs a ``valid_until`` at most ``MAXIMUM_AGENT_WINDOW`` after it starts. Open-ended
or longer restrictions on other agents are the owner's own (Web/API).
"""

from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_contracts.trading_restrictions import AgentRestrictionRequest, RestrictionListQuery
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, fixed_market
from lonora_db.owner_words import owner_typed_message
from lonora_db.runs import require_lease
from lonora_db.schema import (
    AgentRow,
    EffectReceiptRow,
    MessageRow,
    RunRow,
    TradingJournalRow,
    TradingRestrictionRow,
)
from lonora_db.supervision import check_cycle, record_intervention, supervises, supervises_all
from lonora_db.trading_restrictions import (
    create_restriction,
    list_restrictions,
    relevant_to,
    restriction_data,
)
from lonora_trading.execution_quality import execution_policy
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .symbols import restriction_symbol

# Runs started by the owner's own message in a conversation or group.
OWNER_TRIGGERS = frozenset({"user", "group"})
# Longest restriction an agent may record for other agents ("this month" at most).
MAXIMUM_AGENT_WINDOW = timedelta(days=31)


def external_content_key(run_id: str) -> str:
    """The receipt that marks a Run as having read content others wrote."""
    return "external-content:" + run_id


async def mark_external_content(session: AsyncSession, run_id: str, tool: str) -> None:
    """Record, once per Run, that a tool returned third-party or other-agent content
    into it (web pages, feeds, MCP servers, peers' memory, stored files, another model).
    Concurrent reads of one segment insert it once."""
    await session.execute(
        insert(EffectReceiptRow)
        .values(key=external_content_key(run_id), result={"tool": tool}, created_at=utcnow())
        .on_conflict_do_nothing(index_elements=[EffectReceiptRow.key])
    )


async def external_content_seen(session: AsyncSession, run: RunRow, after_seq: int) -> bool:
    """Whether this Run has read content someone other than the owner wrote: a tool
    result of that kind (``mark_external_content``) or another agent's message (a peer's
    outcome, a group reply) after the owner's message it answers."""
    if await session.get(EffectReceiptRow, external_content_key(run.id)) is not None:
        return True
    other = await session.scalar(
        select(MessageRow.id)
        .where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.seq > after_seq,
            MessageRow.seq <= run.input_seq,
            MessageRow.agent_id.is_not(None),
            MessageRow.agent_id != run.agent_id,
        )
        .limit(1)
    )
    return other is not None


async def owner_message_id(session: AsyncSession, run: RunRow) -> str | None:
    """The owner's latest message this run answers, or None for non-owner wakes.

    It stands for the owner's intent only while the Run has read nothing someone else
    wrote: once a web page, feed, MCP result, peer's memory or another agent's message
    reached it, injected text could steer the call, so it is None and the sensitive
    tools (supervision, agent creation and control, the owner profile and reach-me,
    model switches, narrowing other agents, lifting a hold, deleting a saved secret)
    fall back to the owner's card or refusal.
    """
    if run.trigger not in OWNER_TRIGGERS:
        return None
    # Only the owner's typed words: a card's send or a follow-up tap never stands for the
    # owner, and a Run a card submission started has none (GENUI_PLAN §8.4).
    found = await owner_typed_message(session, run)
    if found is None:
        return None
    if await external_content_seen(session, run, int(found.seq)):
        return None
    return str(found.id)


async def other_agents(session: AsyncSession, context: ToolContext) -> list[str]:
    return list(
        await session.scalars(
            select(AgentRow.id).where(
                AgentRow.owner_id == context.owner_id, AgentRow.id != context.agent_id
            )
        )
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
        if not replayed and scoped_agent != context.agent_id:
            # Narrowing another agent needs the owner's message in this run or a
            # supervision grant over it (over every agent, for all agents); and an agent
            # never narrows one that holds an active pause over it, unless the owner asks.
            if message_id is None and not (
                await supervises_all(session, context.owner_id, context.agent_id)
                if scoped_agent is None
                else await supervises(session, context.owner_id, context.agent_id, scoped_agent)
            ):
                raise LonoraError("restriction_supervision_required", 403)
            await check_cycle(
                session,
                context.owner_id,
                context.agent_id,
                [scoped_agent] if scoped_agent else await other_agents(session, context),
                owner_message=message_id is not None,
            )
            # Binding other agents is a time-boxed pause, never an open-ended freeze.
            if params.valid_until is None:
                raise LonoraError("restriction_valid_until_required", 422)
            if params.valid_until - max(params.valid_from or utcnow(), utcnow()) > (
                MAXIMUM_AGENT_WINDOW
            ):
                raise LonoraError("restriction_window_too_long", 422)
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
        if not replayed and scoped_agent != context.agent_id:
            record_intervention(
                session,
                context.owner_id,
                actor_id=context.agent_id,
                agent_id=scoped_agent or context.agent_id,
                payload={
                    "action": "restrict",
                    "target": "restriction",
                    "target_id": row.id,
                    "all_agents": scoped_agent is None,
                    "source": "owner_message" if message_id else "agent",
                },
                run_id=run.id,
            )
        query = select(TradingJournalRow).where(
            TradingJournalRow.owner_id == context.owner_id,
            TradingJournalRow.account_id == row.account_id,
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
            "all_mutations (no other broker changes; for another agent or all agents only "
            "when the owner's message asked). A restriction you record never blocks closes, "
            "cancellations or tighter stops; only the owner's own freeze does. Scope: account "
            "(default your bound account); symbol (the broker must list it; your home market "
            "by default on your home account) or all_symbols for every symbol on the account "
            "(not for a market-bound agent); yourself by default, another agent_id (one you "
            "supervise, or when the owner's message asked) or all_agents. Set valid_until for a time-limited instruction such as 'today' (end "
            "of the owner's day, timezone-aware); it is required, within 31 days, for another "
            "agent or all agents, and may be omitted only for an open-ended one on yourself. "
            "It only narrows: watches and analysis continue, existing positions and pending "
            "orders are not changed, and an already submitted operation is not reversed, so "
            "check and report those separately. Only the owner can lift a restriction.",
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
