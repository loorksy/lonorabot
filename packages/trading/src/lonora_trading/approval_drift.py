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
            if row.validity.get("reference") and row.validity.get("tolerance")
        ]
    quotes: dict[tuple[str, str], Quote | None] = {}
    drifted = 0
    for row in rows:
        reference = row.validity["reference"]
        key = (str(reference["account_id"]), str(reference["symbol"]))
        if key not in quotes:
            try:
                broker = await brokers.get(owner_id, key[0])
                quotes[key] = await broker.quote(key[1])
            except Exception:
                quotes[key] = None  # No quote now: the next tick reads it again.
        quote = quotes[key]
        if quote is None or not outside(quote, row.validity):
            continue
        async with db.sessions() as session, session.begin():
            try:
                locked, run = await locked_approval(session, owner_id, row.id)
            except LonoraError:
                continue  # Its conversation was deleted: it can no longer be decided.
            if locked.status != "pending":
                continue
            await end_card(session, locked, run, "drifted", drifted_prompt(locked))
        drifted += 1
    return drifted
