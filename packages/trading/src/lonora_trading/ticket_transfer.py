"""A deleted agent's open positions and pending orders transfer to Lonora (mandate 3.1.2).

Ownership stays derived (3.3.4): a ticket belongs to the agent whose journaled order
opened it, and once that agent no longer exists it is Lonora's (``account_authority.
ticket_agent``). Nothing is rewritten in the journal. At the delete, the tickets the
deleted agent opened are read from each account's last broker observation, and Lonora
is woken with them: one server-written broker event per account, under Lonora's own
mode, in a work thread whose result returns to Lonora's conversation.
"""

import re
from typing import Any

from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_db.runs import create_run
from lonora_db.schema import AgentRow, BrokerSessionRow, TradingJournalRow
from lonora_db.threads import conversation_thread, create_thread
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import opening_agent

# Broker strings go into the wake's server text: only identifier characters survive.
_UNSAFE = re.compile(r"[^A-Za-z0-9._#-]")
# One wake lists at most this many tickets; the rest are read with account_activity.
LISTED = 50


def _safe(value: object) -> str:
    return _UNSAFE.sub("", str(value))[:64]


async def opened_tickets(
    session: AsyncSession, owner_id: str, agent_id: str
) -> list[dict[str, str]]:
    """The positions and pending orders ``agent_id`` opened, from each account's last
    observation; ordered by account, kind and ticket."""
    tickets: list[dict[str, str]] = []
    accounts = await session.scalars(
        select(BrokerSessionRow)
        .where(BrokerSessionRow.owner_id == owner_id)
        .order_by(BrokerSessionRow.id)
    )
    for account in accounts:
        raw = (account.state or {}).get("broker_recovery")
        if not raw:
            continue
        snapshot = BrokerRecoverySnapshot.model_validate(raw)
        by_symbol: dict[str, list[TradingJournalRow]] = {}
        for resource, items in (("position", snapshot.positions), ("order", snapshot.orders)):
            for item in sorted(items, key=lambda ticket: ticket.id):
                # Per symbol, as ticket_agent reads it, so a busy account's other symbols
                # never push an old opening out of the window.
                entries = by_symbol.get(item.symbol)
                if entries is None:
                    entries = by_symbol[item.symbol] = list(
                        await session.scalars(
                            select(TradingJournalRow)
                            .where(
                                TradingJournalRow.owner_id == owner_id,
                                TradingJournalRow.account_id == account.id,
                                TradingJournalRow.request["symbol"].as_string() == item.symbol,
                                TradingJournalRow.request["action"]
                                .as_string()
                                .in_(sorted(ENTRY_ACTIONS)),
                            )
                            .order_by(TradingJournalRow.updated_at.desc())
                            .limit(1000)
                        )
                    )
                if opening_agent(item, entries) == agent_id:
                    tickets.append(
                        {
                            "account_id": account.id,
                            "resource": resource,
                            "ticket": item.id,
                            "symbol": item.symbol,
                            "volume": str(item.volume),
                        }
                    )
    return tickets


def transfer_prompt(agent_id: str, tickets: list[dict[str, str]], *, paused: bool = False) -> str:
    """Fixed text, server identifiers and sanitized broker values only."""
    listed = "; ".join(
        f"account_id={_safe(t['account_id'])} {_safe(t['resource'])} "
        f"ticket={_safe(t['ticket'])} symbol={_safe(t['symbol'])} volume={_safe(t['volume'])}"
        for t in tickets[:LISTED]
    )
    more = f" and {len(tickets) - LISTED} more" if len(tickets) > LISTED else ""
    return (
        f"The team agent agent_id={_safe(agent_id)} was deleted. Its open positions and "
        f"pending orders are now yours: {listed}{more}. Use account_activity and the current "
        "account state to reassess each and decide what to do under your mode. Never resend "
        "an uncertain operation."
    ) + (
        # The same line a paused agent's own broker wake carries (4.7.1).
        " You are paused: only risk-reducing requests are sent (a full or partial close, "
        "cancelling a pending order, adding a stop loss, or moving a stop loss toward the "
        "market); take no new work."
        if paused
        else ""
    )


async def wake_lonora(
    session: AsyncSession,
    owner_id: str,
    lonora: AgentRow,
    agent_id: str,
    tickets: list[dict[str, str]],
) -> list[str]:
    """One wake of Lonora per account holding transferred tickets; the run ids."""
    by_account: dict[str, list[dict[str, str]]] = {}
    for ticket in tickets:
        by_account.setdefault(ticket["account_id"], []).append(ticket)
    if not by_account:
        return []
    thread = await conversation_thread(session, owner_id, lonora.id)
    started: list[str] = []
    for account_id, items in by_account.items():
        work = await create_thread(
            session, owner_id, ThreadCreate(agent_id=lonora.id), purpose="work"
        )
        metadata: dict[str, Any] = {
            "origin_thread_id": thread.id,
            "account_id": account_id,
            "transferred_from": agent_id,
            "tickets": [_safe(item["ticket"]) for item in items[:LISTED]],
        }
        run = await create_run(
            session,
            owner_id,
            RunRequest(
                thread_id=work.id,
                agent_id=lonora.id,
                trigger="broker_event",
                prompt=transfer_prompt(agent_id, items, paused=lonora.paused),
                metadata=metadata,
            ),
            stable_id(agent_id, "transfer:" + account_id),
        )
        started.append(run.id)
    return started
