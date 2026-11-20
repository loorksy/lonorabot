"""The server records a lonora-ui trusted slot may reference (mandate 10.2, docs/genui.md).

A slot names a fixed card kind and a record id; the compiler places it only when that
record exists, belongs to this owner, sits in this conversation and is of that kind. The
clients draw everything inside the slot from the live record, never from the card.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .owner_actions import account_facts
from .schema import (
    AgentRow,
    BrokerSessionRow,
    OwnerActionRow,
    RunRow,
    TradeApprovalRow,
    TradingJournalRow,
)


@dataclass(frozen=True)
class SlotRecord:
    """What a slot's fixed card draws that sets its height, as the record is when the card is
    compiled (mandate 10.1.4): whether it still waits for the owner, its rows (an approval's
    requests, a Secret card's fields) and the texts that wrap: the agent's reason on an
    approval; the agent a Mandate, Settle or Secret card names; a Settle card's operation and
    account; a Secret card's own label, the name it was given, its field labels and, on a
    broker card, its account."""

    waiting: bool = True
    rows: int = 1
    reason: str = ""
    name: str = ""
    operation: str = ""
    account: str = ""
    label: str = ""
    detail: str = ""
    labels: tuple[str, ...] = ()
    broker: bool = False


def _text(value: Any) -> str:
    return str(value) if isinstance(value, str | int | float) and value != "" else ""


async def slot_records(
    session: AsyncSession, owner_id: str, run_id: str | None, thread_id: str, ids: Iterable[str]
) -> dict[tuple[str, str], SlotRecord]:
    """``(card, record id)`` for every named record a slot of this reply may show, with what its
    card draws that sets its height. The reply's conversation is its Run's origin conversation
    when the Run works in its own thread (a broker event, a watch): its reply, approvals and
    cards land there (``outcome_return``)."""
    wanted = sorted(set(ids))
    run = await session.get(RunRow, run_id) if run_id else None
    origin = run.model_metadata.get("origin_thread_id") if run is not None else None
    thread_id = origin if isinstance(origin, str) and origin else thread_id
    if not wanted or not thread_id:
        return {}
    found: dict[tuple[str, str], SlotRecord] = {}
    approvals = await session.scalars(
        select(TradeApprovalRow).where(
            TradeApprovalRow.id.in_(wanted),
            TradeApprovalRow.owner_id == owner_id,
            TradeApprovalRow.thread_id == thread_id,
        )
    )
    for approval in approvals:
        found[("trade_approval", approval.id)] = SlotRecord(
            waiting=approval.status == "pending",
            rows=max(len(approval.requests), 1),
            reason=approval.reason or "",
        )
    cards = list(
        await session.scalars(
            select(OwnerActionRow).where(
                OwnerActionRow.id.in_(wanted),
                OwnerActionRow.owner_id == owner_id,
                OwnerActionRow.thread_id == thread_id,
                OwnerActionRow.kind.in_(("settle_operation", "secret", "trading_mode")),
            )
        )
    )
    # The agent each card names: a Mandate card's agent, a Secret card's asker, the agent that
    # sent a Settle card's operation (none: «an agent», or the owner's own order).
    named: dict[str, str] = {}
    journals: dict[str, TradingJournalRow] = {}
    for card in cards:
        if card.kind == "trading_mode":
            named[card.id] = _text(card.payload.get("agent_id"))
        elif card.kind == "secret":
            named[card.id] = card.agent_id or ""
        else:
            journal = await session.get(TradingJournalRow, card.payload.get("operation_id"))
            if journal is None:
                continue
            journals[card.id] = journal
            details: Any = journal.result.get("details")
            execution: Any = (
                cast(dict[str, Any], details).get("execution")
                if isinstance(details, dict)
                else None
            )
            named[card.id] = _text(
                cast(dict[str, Any], execution).get("agent_id")
                if isinstance(execution, dict)
                else None
            )
    agents = sorted({identity for identity in named.values() if identity})
    names: dict[str, str] = (
        {
            row.id: row.name
            for row in await session.scalars(
                select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.id.in_(agents))
            )
        }
        if agents
        else {}
    )
    for card in cards:
        name = names.get(named.get(card.id, ""), "")
        payload = card.payload
        waiting = card.status == "pending"
        if card.kind == "trading_mode":
            found[("mandate", card.id)] = SlotRecord(waiting=waiting, name=name)
        elif card.kind == "secret":
            fields = cast(list[dict[str, Any]], payload.get("fields") or [])
            account = cast(dict[str, Any], payload.get("account") or {})
            found[("secret", card.id)] = SlotRecord(
                waiting=waiting,
                rows=len(fields),
                name=name,
                label=_text(payload.get("label")),
                detail=_text(cast(dict[str, Any], payload.get("details") or {}).get("name")),
                labels=tuple(
                    _text(field.get("label")) or _text(field.get("key")) for field in fields
                ),
                broker=bool(account),
                account=" ".join(
                    _text(account.get(key)) for key in ("login", "server", "platform")
                ),
            )
        else:
            journal = journals.get(card.id)
            request = journal.request if journal is not None else {}
            session_row = (
                await session.get(BrokerSessionRow, journal.account_id) if journal else None
            )
            found[("settle", card.id)] = SlotRecord(
                waiting=waiting,
                name=name,
                operation=" ".join(
                    _text(request.get(key)) for key in ("action", "volume", "symbol")
                ),
                account=_text(
                    account_facts(session_row, journal.account_id).get("label")
                    if journal is not None
                    else ""
                ),
            )
    return found
