"""The owner's ``position_unprotected`` item: a close left a position without protection.

A broker whose stop-loss lives in separate exit orders (Alpaca) closes a protected
position in steps: release the exit orders, close, re-arm what is still held. When the
re-arming could not be done, or the close outcome is unknown, the adapter reports
``details.protection.restored == False``. The executor raises one item per operation,
and it stays open until the broker shows that position protected again or closed;
the operation settling later does not clear it.
"""

import logging
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.attention import raise_system_attention, settle_system_attention
from lonora_db.client import Database
from lonora_db.item_failures import failure_code
from lonora_db.schema import AttentionRow, RunRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CODE = "position_unprotected"
log = logging.getLogger("lonora.protection")


def protection_lost(result: TradeResult) -> bool:
    record: Any = result.details.get("protection")
    return isinstance(record, dict) and cast(dict[str, Any], record).get("restored") is False


async def raise_unprotected(
    session: AsyncSession,
    owner_id: str,
    request: TradeRequest,
    result: TradeResult,
    lease: Lease | None,
) -> None:
    if not protection_lost(result):
        return
    run = await session.get(RunRow, lease.run_id) if lease else None
    await raise_system_attention(
        session,
        owner_id,
        CODE,
        request.operation_id,
        {
            "operation_id": request.operation_id,
            "account_id": request.account_id,
            "symbol": request.symbol,
            "position_id": request.position_id,
        },
        agent_id=run.agent_id if run else None,
        thread_id=run.thread_id if run else None,
    )


async def recheck_protection(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """Withdraw items whose position is protected again or closed. Reads only."""
    async with db.sessions() as session:
        items = list(
            await session.scalars(
                select(AttentionRow)
                .where(
                    AttentionRow.owner_id == owner_id,
                    AttentionRow.code == CODE,
                    AttentionRow.status.in_(["pending", "ready"]),
                )
                .limit(50)
            )
        )
    settled = 0
    for item in items:
        parameters = item.parameters
        try:
            broker = await brokers.get(owner_id, str(parameters.get("account_id", "")))
            positions = await broker.positions()
        except Exception as error:
            # Unobservable is not evidence of protection: the item stays open.
            log.warning("protection_recheck_failed code=%s", failure_code(error))
            continue
        position = next((p for p in positions if p.id == parameters.get("position_id")), None)
        if position is not None and position.stop_loss is None:
            continue
        async with db.sessions() as session, session.begin():
            settled += int(
                await settle_system_attention(
                    session, owner_id, CODE, str(parameters.get("operation_id", ""))
                )
            )
    return settled
