"""The Execution Receipt (mandate 10.3, 11.2): one per broker-confirmed operation.

``post_receipt`` runs inside ``persist_result``, in the transaction that records the
broker's confirmation, so every path that confirms an operation (the door's own send,
reconciliation, recovery after a restart) posts exactly one receipt, and nothing else
does: model text, a generated card and the owner's settlement never reach it. The
receipt row only says where it was posted; what it shows is read from the journal row.
"""

from typing import Any, cast

from lonora_contracts.trading import TradeRequest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, ExecutionReceiptRow, RunRow, ThreadRow, TradingJournalRow
from .threads import conversation_thread

NEW_ORDERS = frozenset({"buy", "sell"})
PENDING_ORDERS = frozenset({"buy_limit", "sell_limit", "buy_stop", "sell_stop"})
MODIFICATIONS = frozenset({"modify_position", "modify_order"})


def _details(row: TradingJournalRow) -> dict[str, Any]:
    details = (row.result or {}).get("details", {})
    return cast(dict[str, Any], details) if isinstance(details, dict) else {}


def _execution(row: TradingJournalRow) -> dict[str, Any]:
    execution = _details(row).get("execution")
    return cast(dict[str, Any], execution) if isinstance(execution, dict) else {}


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def receipt_facts(row: TradingJournalRow) -> dict[str, Any]:
    """The broker-confirmed facts of a confirmed operation, by its kind (10.3).

    Fills: ticket, action, volume, fill price (as the broker reported them). A placed
    pending order: its ticket and the order the broker accepted. Modifications: the ticket
    and its new values. Cancels: the ticket.
    """
    request = TradeRequest.model_validate(row.request)
    details = _details(row)
    result = row.result or {}
    if request.action in NEW_ORDERS or request.action in PENDING_ORDERS:
        ticket = (
            _text(details.get("position_id"))
            if request.action in NEW_ORDERS
            else _text(details.get("order_id"))
        ) or _text(result.get("broker_id"))
    else:
        # An existing ticket: the broker confirmed the change to the ticket that was named.
        ticket = request.position_id or request.order_id or _text(result.get("broker_id"))
    facts: dict[str, Any] = {"action": request.action, "symbol": request.symbol, "ticket": ticket}
    if request.action in NEW_ORDERS or request.action == "close_position":
        # The volume and price the broker reports it executed; a full fill without a
        # reported volume executed the volume that was asked.
        volume = _text(details.get("volume"))
        if volume is None and not details.get("partial_execution") and request.volume:
            volume = format(request.volume, "f")
        facts |= {
            "kind": "fill",
            "volume": volume,
            "price": _text(details.get("price")) or _text(details.get("execution_price")),
            "partial": bool(details.get("partial_execution")),
        }
    elif request.action in PENDING_ORDERS:
        facts |= {
            "kind": "order",
            "volume": format(request.volume, "f") if request.volume else None,
            "price": format(request.price, "f") if request.price else None,
            "stop_loss": format(request.stop_loss, "f") if request.stop_loss else None,
            "take_profit": format(request.take_profit, "f") if request.take_profit else None,
        }
    elif request.action in MODIFICATIONS:
        facts |= {
            "kind": "modify",
            "price": format(request.price, "f") if request.price else None,
            "stop_loss": format(request.stop_loss, "f") if request.stop_loss else None,
            "take_profit": format(request.take_profit, "f") if request.take_profit else None,
            "stop_loss_removed": request.clear_stop_loss,
            "take_profit_removed": request.clear_take_profit,
        }
    else:
        facts |= {"kind": "cancel"}
    return facts


async def _posting_thread(session: AsyncSession, row: TradingJournalRow) -> ThreadRow | None:
    """The conversation of the run that requested it; else the requesting agent's own
    conversation; for the owner's own order, Lonora's conversation."""
    if row.thread_id is not None:
        thread = await session.get(ThreadRow, row.thread_id)
        if thread is not None:
            return thread
    execution = _execution(row)
    run_id = execution.get("run_id")
    if isinstance(run_id, str) and run_id:
        run = await session.get(RunRow, run_id)
        if run is not None:
            origin = run.model_metadata.get("origin_thread_id")
            thread = await session.get(
                ThreadRow, origin if isinstance(origin, str) and origin else run.thread_id
            )
            if thread is not None and thread.owner_id == row.owner_id:
                return thread
    agent_id = execution.get("agent_id")
    if not (isinstance(agent_id, str) and agent_id and await session.get(AgentRow, agent_id)):
        # The owner's own order, or an agent deleted meanwhile (its tickets are Lonora's).
        agent_id = await session.scalar(
            select(AgentRow.id).where(
                AgentRow.owner_id == row.owner_id, AgentRow.role == "personal"
            )
        )
    if agent_id is None:
        return None
    return await conversation_thread(session, row.owner_id, agent_id)


async def post_receipt(session: AsyncSession, row: TradingJournalRow) -> bool:
    """Post the receipt of ``row``, which this transaction has just confirmed.

    The operation id is the receipt's key: a second call (a replay, a later observer)
    inserts nothing. Returns whether this call posted it.
    """
    if row.status != "confirmed":
        return False
    agent_id = _execution(row).get("agent_id")
    agent_id = agent_id if isinstance(agent_id, str) and agent_id else None

    async def insert_receipt(thread: ThreadRow | None) -> str | None:
        return await session.scalar(
            insert(ExecutionReceiptRow)
            .values(
                operation_id=row.operation_id,
                owner_id=row.owner_id,
                agent_id=agent_id,
                thread_id=thread.id if thread is not None else None,
                timeline_seq=thread.next_seq if thread is not None else None,
            )
            .on_conflict_do_nothing(index_elements=[ExecutionReceiptRow.operation_id])
            .returning(ExecutionReceiptRow.operation_id)
        )

    try:
        async with session.begin_nested():
            thread = await _posting_thread(session, row)
            posted = await insert_receipt(thread)
    except Exception:
        # Where it is posted never stands between the broker's confirmation and the
        # journal: the receipt is kept, without a conversation, rather than lost with it.
        thread = None
        posted = await insert_receipt(None)
    if posted is None:
        return False
    # Clients refresh the conversation; an Execution Receipt never sends a push (11.4).
    emit(
        session,
        row.owner_id,
        "trading.receipt_posted",
        thread_id=thread.id if thread is not None else None,
        agent_id=agent_id,
        payload={"operation_id": row.operation_id},
    )
    return True


def receipt_data(receipt: ExecutionReceiptRow, row: TradingJournalRow) -> dict[str, Any]:
    verification = _details(row).get("verification")
    status = (
        cast(dict[str, Any], verification).get("status") if isinstance(verification, dict) else None
    )
    annotation = row.annotation or {}
    reason = str(annotation.get("reason") or "").strip() if receipt.agent_id else ""
    return {
        "operation_id": receipt.operation_id,
        "thread_id": receipt.thread_id,
        "timeline_seq": receipt.timeline_seq,
        # None: the owner's own order, which shows no reason.
        "agent_id": receipt.agent_id,
        "created_at": receipt.created_at.isoformat(),
        **receipt_facts(row),
        # The agent's own words, stored beside the request; shown labelled as the agent's.
        "reason": reason or None,
        # Broker-confirmed; "pending" until the resulting account state is read back.
        "verification": status if status in {"pending", "verified", "unverified"} else None,
    }


async def thread_receipts(
    session: AsyncSession, owner_id: str, thread_id: str
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(ExecutionReceiptRow, TradingJournalRow)
        .join(
            TradingJournalRow,
            TradingJournalRow.operation_id == ExecutionReceiptRow.operation_id,
        )
        .where(ExecutionReceiptRow.owner_id == owner_id, ExecutionReceiptRow.thread_id == thread_id)
        .order_by(ExecutionReceiptRow.created_at.desc())
        .limit(500)
    )
    return [receipt_data(receipt, row) for receipt, row in reversed(list(rows.tuples()))]


async def receipt_thread(session: AsyncSession, operation_id: str) -> str | None:
    return await session.scalar(
        select(ExecutionReceiptRow.thread_id).where(
            ExecutionReceiptRow.operation_id == operation_id
        )
    )
