"""One measured read-only evidence capability, available to the normal Agent."""

import asyncio
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle
from lonora_contracts.relationships import RelationshipReference, RelationshipRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_market_binding
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.relationships import read_relationship, relationship_summary, save_relationship
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow
from lonora_market.broker import broker_market
from lonora_market.relationships import measure_relationship
from lonora_session.idempotency import request_hash

from .base import Tool
from .context import ToolContext


async def check_scope(
    context: ToolContext, account_id: str, symbols: list[str], *, require_connection: bool = True
) -> None:
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        assert_market_binding(agent, account_id)
        if agent.trading_symbol and agent.trading_symbol not in symbols:
            raise LonoraError("agent_trading_symbol_mismatch", 409)
        if require_connection:
            await BrokerSessionRepository().get(session, context.owner_id, account_id)


async def record(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = RelationshipRequest.model_validate(args)
    await check_scope(context, params.account_id, params.symbols)
    intent = request_hash(params.model_dump(mode="json"))
    async with context.db.sessions() as session:
        previous = await session.get(EffectReceiptRow, "relationship:" + context.resource_id)
        if previous:
            if previous.result["intent"] != intent:
                raise LonoraError("relationship_intent_conflict", 409)
            return relationship_summary(
                await read_relationship(session, context.owner_id, context.resource_id)
            )
    market = await broker_market(context.brokers, context.owner_id, params.account_id)
    missing: list[str] = []

    async def fetch(symbol: str) -> list[Candle]:
        try:
            async with asyncio.timeout(20):
                return await market.candles(symbol, params.timeframe, params.window * 2 + 2)
        except (LonoraError, TimeoutError) as error:
            missing.append(
                error.code if isinstance(error, LonoraError) else "relationship_history_timeout"
            )
            return []

    series = list(await asyncio.gather(*(fetch(symbol) for symbol in params.symbols)))
    value = measure_relationship(
        params,
        series,
        identifier=context.resource_id,
        owner_id=context.owner_id,
        agent_id=context.agent_id,
        now=utcnow(),
    )
    value.reason_codes = list(dict.fromkeys(value.reason_codes + missing))[:8]
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        return relationship_summary(
            await save_relationship(
                session,
                value,
                intent=intent,
                thread_id=context.thread_id,
                run_id=context.lease.run_id,
            )
        )


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = RelationshipReference.model_validate(args)
    async with context.db.sessions() as session:
        value = await read_relationship(session, context.owner_id, params.relationship_id)
    await check_scope(context, value.account_id, value.symbols, require_connection=False)
    return relationship_summary(value)


def tools() -> list[Tool]:
    return [
        Tool(
            "market_relationship_record",
            "Measure and persist cross-market evidence from time-aligned closed broker bars. Specify two exact symbols and a bounded window; recent and baseline windows do not overlap. A specialist's bound symbol must be one member. Correlation is not causation or a trade instruction; unavailable evidence stays unavailable.",
            RelationshipRequest,
            record,
        ),
        Tool(
            "market_relationship_read",
            "Read immutable measured relationship evidence by its recorded ID, without substituting today's market. No execution authority is granted.",
            RelationshipReference,
            read,
            True,
        ),
    ]
