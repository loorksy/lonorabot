"""Shared persisted virtual position/order projections; no broker or trading executor."""

from decimal import Decimal

from lonora_contracts.account import Order, Position
from sqlalchemy import select

from .client import Database
from .schema import ShadowTradeRow


async def shadow_rows(
    db: Database,
    owner_id: str,
    agent_id: str,
    account_id: str | None,
    symbol: str | None = None,
    *,
    statuses: tuple[str, ...] | None = None,
) -> list[ShadowTradeRow]:
    async with db.sessions() as session:
        query = select(ShadowTradeRow).where(
            ShadowTradeRow.owner_id == owner_id,
            ShadowTradeRow.agent_id == agent_id,
        )
        if account_id:
            query = query.where(ShadowTradeRow.account_id == account_id)
        if symbol:
            query = query.where(ShadowTradeRow.symbol == symbol)
        if statuses:
            query = query.where(ShadowTradeRow.status.in_(statuses))
        return list(
            await session.scalars(query.order_by(ShadowTradeRow.created_at.desc()).limit(1000))
        )


def shadow_position(row: ShadowTradeRow) -> Position:
    return Position(
        id=row.id,
        symbol=row.symbol,
        side=row.payload["side"],
        volume=Decimal(row.state["remaining_volume"]),
        open_price=Decimal(row.state["entry_price"]),
        stop_loss=Decimal(row.state["stop_loss"]) if row.state.get("stop_loss") else None,
        take_profit=Decimal(row.state["take_profit"]) if row.state.get("take_profit") else None,
        operation_id=row.payload["operation_id"],
    )


def shadow_order(row: ShadowTradeRow) -> Order:
    return Order(
        id=row.id,
        symbol=row.symbol,
        side=row.payload["action"],
        volume=Decimal(row.state["remaining_volume"]),
        price=Decimal(row.payload["price"]),
        stop_loss=Decimal(row.state["stop_loss"]) if row.state.get("stop_loss") else None,
        take_profit=Decimal(row.state["take_profit"]) if row.state.get("take_profit") else None,
        operation_id=row.payload["operation_id"],
    )
