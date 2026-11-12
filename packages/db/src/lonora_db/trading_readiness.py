"""Presentation-only trading readiness: can this agent trade now, and what stops it.

One bounded projection for the owner's header safety pill, its sheet and the agent's
status line. It is built from the same records the financial boundary reads: the
agent's ladder level and signed grants, and each account's unresolved operations with
their scoped block.

It is never consulted for enforcement. The single executor re-reads every one of
these at the moment of sending (``lonora_trading.execution``), so a stale or wrong
projection can at most show the owner an outdated line; it can never admit a trade.
"""

from datetime import datetime
from typing import Any, cast

from lonora_contracts.account_authority import full_delegation
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import UNRESOLVED_STATUSES
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import fixed_market
from .agent_permissions import permission_state
from .schema import (
    AgentRow,
    BrokerSessionRow,
    OwnerActionRow,
    ThreadRow,
    TradingJournalRow,
)

ACCOUNT_LIMIT = 10
LIST_LIMIT = 5


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _producer(row: TradingJournalRow) -> str | None:
    """The agent the executor recorded for this operation; None for the owner's own."""
    details: Any = row.result.get("details")
    execution: Any = (
        cast(dict[str, Any], details).get("execution") if isinstance(details, dict) else None
    )
    agent_id: Any = (
        cast(dict[str, Any], execution).get("agent_id") if isinstance(execution, dict) else None
    )
    return agent_id if isinstance(agent_id, str) else None


async def trading_readiness(
    session: AsyncSession, owner_id: str, agent: AgentRow
) -> dict[str, Any]:
    now = utcnow()
    permission = await permission_state(session, owner_id, agent.id)
    level: str = permission["effective_level"]
    grants: list[dict[str, Any]] = []
    for row in permission["active_authorities"][:3]:
        envelope: dict[str, Any] = row["envelope"]
        grants.append(
            {
                "account_id": row["account_id"],
                "symbol_scope": envelope.get("symbol_scope", "selected"),
                "symbols": list(envelope.get("symbols", []))[:20],
                "actions": list(envelope.get("actions", []))[:10],
                "allow_manual_positions": bool(envelope.get("allow_manual_positions")),
                "valid_until": row["valid_until"],
                # Every pair, every action and the owner's own positions, until revoked.
                "full_delegation": full_delegation(envelope),
            }
        )
    accounts_query = (
        select(BrokerSessionRow.id)
        .where(BrokerSessionRow.owner_id == owner_id)
        .order_by(BrokerSessionRow.created_at, BrokerSessionRow.id)
    )
    if fixed_market(agent):
        accounts_query = accounts_query.where(BrokerSessionRow.id == agent.trading_account_id)
    accounts = list(await session.scalars(accounts_query.limit(ACCOUNT_LIMIT)))
    # The accounts the line speaks for: the agent's own market, its signed grants when it
    # trades on its own, otherwise every account it may ask to trade on. The sheet still
    # lists operations on the other accounts, each with its account named.
    granted = {str(row["account_id"]) for row in permission["active_authorities"]}
    # A signed grant's account is always read, however many other accounts the owner has:
    # otherwise its unresolved operations would be missing from the line it speaks for.
    accounts += sorted(granted - set(accounts))
    in_scope = granted if level == "autonomous" and granted else set(accounts)
    operations: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    if accounts:
        scope = [
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.account_id.in_(accounts),
            TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
        ]
        if fixed_market(agent):
            scope.append(
                func.lower(TradingJournalRow.request["symbol"].as_string())
                == (agent.trading_symbol or "").casefold()
            )
        counts = {
            str(account_id): int(count)
            for account_id, count in (
                await session.execute(
                    select(TradingJournalRow.account_id, func.count())
                    .where(*scope)
                    .group_by(TradingJournalRow.account_id)
                )
            ).all()
        }
        for row in await session.scalars(
            select(TradingJournalRow)
            .where(*scope)
            .order_by(TradingJournalRow.submitted_at, TradingJournalRow.operation_id)
            .limit(LIST_LIMIT)
        ):
            operations.append(
                {
                    "operation_id": row.operation_id,
                    "account_id": row.account_id,
                    "symbol": str(row.request.get("symbol", ""))[:80],
                    "action": str(row.request.get("action", ""))[:24],
                    "status": row.status,
                    "submitted_at": _iso(row.submitted_at),
                    "this_agent": _producer(row) == agent.id,
                    # The scoped block: new risk on this market or ticket only, never
                    # the account, never an exit. It is never resent automatically.
                    "blocks": "new_risk_on_this_symbol_or_ticket",
                }
            )
    # «حسم» opens the operation's own resolve card (a live, pending one), never another card,
    # in whichever conversation holds it (this chat, another agent's, a group, Lonora's).
    cards: dict[str, dict[str, Any]] = {}
    if operations:
        for card_id, subject, thread_id, seq, thread_agent, group_id in (
            await session.execute(
                select(
                    OwnerActionRow.id,
                    OwnerActionRow.subject,
                    OwnerActionRow.thread_id,
                    OwnerActionRow.timeline_seq,
                    ThreadRow.agent_id,
                    ThreadRow.group_id,
                )
                .outerjoin(ThreadRow, ThreadRow.id == OwnerActionRow.thread_id)
                .where(
                    OwnerActionRow.owner_id == owner_id,
                    OwnerActionRow.kind == "resolve_operation",
                    OwnerActionRow.status == "pending",
                    OwnerActionRow.expires_at > now,
                    OwnerActionRow.subject.in_(
                        ["operation:" + item["operation_id"] for item in operations]
                    ),
                )
                .order_by(OwnerActionRow.created_at)
            )
        ).all():
            cards[subject.removeprefix("operation:")] = {
                "id": card_id,
                "thread_id": thread_id,
                "agent_id": thread_agent,
                "group_id": group_id,
                "timeline_seq": seq,
            }
    for item in operations:
        item["resolve_card"] = cards.get(item["operation_id"])
    state, params = _headline(
        level=level,
        paused=bool(agent.paused),
        grants=grants,
        operations=[item for item in operations if item["account_id"] in in_scope],
        unresolved_count=sum(
            count for account_id, count in counts.items() if account_id in in_scope
        ),
    )
    return {
        "presentation_only": True,
        "observed_at": now.isoformat(),
        "state": state,
        "params": params,
        "level": level,
        "grants": grants,
        "unresolved_operations": operations,
        "unresolved_count": sum(counts.values()),
    }


def _headline(
    *,
    level: str,
    paused: bool,
    grants: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    unresolved_count: int,
) -> tuple[str, dict[str, Any]]:
    """The one line: the agent's ladder level, or the strongest thing stopping it."""
    if level == "analysis":
        return "no_trading", {}
    if paused:
        return "agent_paused", {}
    if unresolved_count:
        return "uncertain", {
            "count": unresolved_count,
            "symbol": operations[0]["symbol"] if operations else None,
        }
    if level == "supervised":
        return "ask_me", {}
    first_grant = grants[0] if grants else None
    return "on_its_own", {
        "symbol_scope": first_grant["symbol_scope"] if first_grant else "selected",
        "full_delegation": bool(first_grant and first_grant["full_delegation"]),
        "symbols": first_grant["symbols"][:3] if first_grant else [],
        "valid_until": first_grant["valid_until"] if first_grant else None,
        "grant_count": len(grants),
        # Grants on several accounts: the line counts them and the sheet lists each.
        "account_count": len({item["account_id"] for item in grants}),
        "account_id": first_grant["account_id"] if first_grant else None,
    }
