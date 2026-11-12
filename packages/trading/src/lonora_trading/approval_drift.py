"""Trade Approval drift (mandate 10.3.1.2).

A pending card for new risk carries a tolerance and the executable price read when it
was made. The server watches the quote: the first quote outside reference ± tolerance
marks the card ``drifted``. A drifted card cannot be approved, and its agent is woken
with fixed server text naming the card.
"""

from decimal import Decimal
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.market import Quote
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import TradeApprovalRow
from lonora_db.trade_approvals import drifted_prompt, end_card, locked_approval
from sqlalchemy import select


def outside(quote: Quote, validity: dict[str, Any]) -> bool:
    reference = validity["reference"]
    price = quote.ask if reference["side"] == "ask" else quote.bid
    return abs(price - Decimal(str(reference["price"]))) > Decimal(str(validity["tolerance"]))


async def band_quote(
    brokers: BrokerManager, owner_id: str, validity: dict[str, Any]
) -> Quote | None:
    """The card's quote now; None when the broker cannot give one."""
    reference = validity["reference"]
    try:
        broker = await brokers.get(owner_id, str(reference["account_id"]))
        return await broker.quote(str(reference["symbol"]))
    except Exception:
        return None


async def mark_drifted(db: Database, owner_id: str, approval_id: str) -> bool:
    """End a still-pending card as drifted and wake its agent; False if already ended."""
    async with db.sessions() as session, session.begin():
        try:
            locked, run = await locked_approval(session, owner_id, approval_id)
        except LonoraError:
            return False  # Its conversation was deleted: it can no longer be decided.
        if locked.status != "pending":
            return False
        await end_card(session, locked, run, "drifted", drifted_prompt(locked))
    return True


def watched(row: TradeApprovalRow) -> bool:
    return bool(row.validity.get("reference") and row.validity.get("tolerance"))


async def check_drift(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """Mark every pending card whose quote left its band; returns how many drifted."""
    async with db.sessions() as session:
        rows = [
            row
            for row in await session.scalars(
                select(TradeApprovalRow).where(
                    TradeApprovalRow.owner_id == owner_id, TradeApprovalRow.status == "pending"
                )
            )
            if watched(row)
        ]
    quotes: dict[tuple[str, str], Quote | None] = {}
    drifted = 0
    for row in rows:
        reference = row.validity["reference"]
        key = (str(reference["account_id"]), str(reference["symbol"]))
        if key not in quotes:
            # No quote now: the next tick reads it again.
            quotes[key] = await band_quote(brokers, owner_id, row.validity)
        quote = quotes[key]
        if quote is not None and outside(quote, row.validity):
            drifted += await mark_drifted(db, owner_id, row.id)
    return drifted


async def check_band_at_approve(
    db: Database, brokers: BrokerManager, owner_id: str, approval_id: str
) -> None:
    """The quote read when the owner taps Approve: outside the band, the card drifts
    there and then and cannot be approved. Without a quote nothing proves the card is
    still valid, so it is not approved now; the owner may tap again."""
    async with db.sessions() as session:
        row = await session.get(TradeApprovalRow, approval_id)
        if row is None or row.owner_id != owner_id or row.status != "pending" or not watched(row):
            return  # The decision answers with its own code.
        validity = dict(row.validity)
    quote = await band_quote(brokers, owner_id, validity)
    if quote is None:
        raise LonoraError("trade_approval_quote_unavailable", 409)
    if outside(quote, validity) and await mark_drifted(db, owner_id, approval_id):
        raise LonoraError("trade_approval_drifted", 409)
