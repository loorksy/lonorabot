"""Capture broker evidence once; explain historical choices without rereading today's market."""

import asyncio
import hashlib
from typing import Any

from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_contracts.market_health import HealthSnapshot
from lonora_contracts.trading import TradingControl
from lonora_contracts.trading_decision import (
    DecisionCompare,
    DecisionEvidence,
    DecisionHistory,
    DecisionReference,
    DecisionRequest,
    TradingDecision,
)
from lonora_core.chart_controller import validate_timeframe
from lonora_core.runtime_failure import TRANSIENT_READ_CODES
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_market_binding
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.relationships import read_relationship
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, EffectReceiptRow
from lonora_db.trading_decisions import (
    decision_changes,
    decision_excerpt,
    decision_history,
    decision_summary,
    read_decision,
    store_decision,
)
from lonora_db.transactions import SettingsRepository
from lonora_market.health import assess_account, assess_candles, assess_quote, timeframe_age_seconds
from lonora_market.relationships import relationship_usable
from lonora_trading.admission import entry_recovery_status
from lonora_trading.decision_readiness import decision_readiness
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool, eager_for
from .context import ToolContext


def fingerprint(params: DecisionRequest) -> str:
    # Preserve old durable operation identities when the optional evidence is absent.
    absent = {
        name
        for name in ("market_view", "entry_condition", "conditional_entry")
        if getattr(params, name) is None
    }
    if not params.relationship_ids:
        absent.add("relationship_ids")
    return hashlib.sha256(params.model_dump_json(exclude=absent).encode()).hexdigest()


async def record(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = DecisionRequest.model_validate(args)
    validate_timeframe(params.timeframe)
    intent = fingerprint(params)
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        assert_market_binding(agent, params.account_id, params.symbol)
        connection = await BrokerSessionRepository().get(
            session, context.owner_id, params.account_id
        )
        connection_version = connection.version
        prior = await session.get(EffectReceiptRow, "decision:" + context.resource_id)
        if prior:
            if prior.result.get("intent") != intent:
                raise LonoraError("decision_intent_conflict", 409)
            return decision_excerpt(TradingDecision.model_validate(prior.result["decision"]))
    evidence = DecisionEvidence(id=context.resource_id, captured_at=utcnow())
    try:
        async with asyncio.timeout(35):
            # Exact symbols are intentional. No hidden aliases or suffix stripping.
            for kind in ("quote", "candles", "account", "positions", "orders"):
                recovered_code = None
                for attempt in range(2):
                    try:
                        async with asyncio.timeout(5):
                            # Reacquire through the existing manager after a read failure;
                            # a closed adapter must not become a private retry cache.
                            broker = await context.brokers.get(context.owner_id, params.account_id)
                            if kind == "quote":
                                evidence.quote = await broker.quote(params.symbol)
                            elif kind == "candles":
                                evidence.candles = (
                                    await broker.candles(params.symbol, params.timeframe, 100)
                                )[-100:]
                            elif kind == "account":
                                evidence.account = await broker.account()
                                evidence.account.id = params.account_id
                            elif kind == "positions":
                                positions = await broker.positions()
                                evidence.positions = positions[:1000]
                                if len(positions) > 1000:
                                    evidence.missing_codes.append("decision_positions_truncated")
                            else:
                                orders = await broker.orders()
                                evidence.orders = orders[:1000]
                                if len(orders) > 1000:
                                    evidence.missing_codes.append("decision_orders_truncated")
                        if recovered_code:
                            evidence.recovered_read_codes.append(kind + ":" + recovered_code)
                        break
                    except (TimeoutError, LonoraError) as error:
                        code = error.code if isinstance(error, LonoraError) else "tool_read_timeout"
                        if attempt == 0 and code in TRANSIENT_READ_CODES:
                            recovered_code = code
                            await asyncio.sleep(0.1)
                            continue
                        evidence.missing_codes.append(code)
                        break
    except (TimeoutError, LonoraError) as error:
        evidence.missing_codes.append(
            error.code if isinstance(error, LonoraError) else "decision_evidence_timeout"
        )
    now = utcnow()
    health: list[HealthSnapshot] = [
        assess_quote(
            evidence.quote,
            account_id=params.account_id,
            symbol=params.symbol,
            now=now,
            maximum_age_seconds=30,
        ),
        assess_candles(
            evidence.candles,
            account_id=params.account_id,
            symbol=params.symbol,
            timeframe=params.timeframe,
            now=now,
            maximum_age_seconds=timeframe_age_seconds(params.timeframe),
        ),
        assess_account(
            evidence.account, account_id=params.account_id, now=now, maximum_age_seconds=60
        ),
    ]
    evidence.health = health
    evidence.captured_at = now
    async with context.db.sessions() as session:
        for identifier in dict.fromkeys(params.relationship_ids):
            relationship = await read_relationship(session, context.owner_id, identifier)
            if (
                relationship.account_id != params.account_id
                or params.symbol not in relationship.symbols
            ):
                raise LonoraError("relationship_scope_mismatch", 409)
            evidence.relationships.append(relationship)
            if not relationship_usable(relationship, now):
                evidence.missing_codes.append("relationship_evidence_unreliable")
    evidence.missing_codes = list(dict.fromkeys(evidence.missing_codes))[:8]
    gates = list(
        dict.fromkeys([h.reason_code for h in health if not h.healthy] + evidence.missing_codes)
    )
    async with context.db.sessions() as session:
        current_connection = await BrokerSessionRepository().get(
            session, context.owner_id, params.account_id
        )
        config = BrokerConnection.model_validate(current_connection.payload)
        controls = TradingControl.model_validate(
            await SettingsRepository().get(session, "trading_control")
        )
        recovery = current_connection.state.get("broker_recovery")
        readiness = decision_readiness(
            params,
            evidence,
            controls=controls,
            broker_enabled=config.enabled,
            broker_recovery_status=await entry_recovery_status(
                session, context.owner_id, params.account_id, params.symbol, recovery
            ),
            connection_changed=current_connection.version != connection_version,
        )
    decision = TradingDecision(
        id=context.resource_id,
        owner_id=context.owner_id,
        agent_id=context.agent_id,
        run_id=context.lease.run_id,
        account_id=params.account_id,
        symbol=params.symbol,
        timeframe=params.timeframe,
        recorded_at=now,
        requested_action=params.action,
        # Operational availability cannot silently rewrite the model's intent.
        # Readiness records missing evidence and execution blockers separately.
        action=params.action,
        conditional_entry=params.conditional_entry,
        summary=params.summary,
        gate_codes=gates,
        evidence=evidence,
        readiness=readiness,
    )
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        return decision_excerpt(
            await store_decision(session, decision, thread_id=context.thread_id, intent=intent)
        )


async def authors(
    session: AsyncSession, context: ToolContext, agent_ids: set[str]
) -> dict[str, Any]:
    """Who recorded each decision: decisions on owner accounts are shared operational records."""
    names: dict[str, str] = {}
    if agent_ids:
        query = select(AgentRow).where(
            AgentRow.owner_id == context.owner_id, AgentRow.id.in_(agent_ids)
        )
        for row in await session.scalars(query):
            names[row.id] = row.name
    return {
        identifier: {
            "agent_id": identifier,
            "name": names.get(identifier),
            "you": identifier == context.agent_id,
        }
        for identifier in agent_ids
    }


async def history(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = DecisionHistory.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        rows = await decision_history(
            session,
            context.owner_id,
            account_id=params.account_id or agent.trading_account_id,
            symbol=params.symbol
            or (
                agent.trading_symbol
                if not params.account_id or params.account_id == agent.trading_account_id
                else None
            ),
            limit=params.limit,
        )
        recorded_by = await authors(session, context, {row.agent_id for row in rows})
        return {
            "decisions": [
                {**decision_summary(row), "recorded_by": recorded_by[row.agent_id]} for row in rows
            ]
        }


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = DecisionReference.model_validate(args)
    async with context.db.sessions() as session:
        row = await read_decision(session, context.owner_id, params.decision_id)
        recorded_by = await authors(session, context, {row.agent_id})
        return {**decision_excerpt(row), "recorded_by": recorded_by[row.agent_id]}


async def compare(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = DecisionCompare.model_validate(args)
    async with context.db.sessions() as session:
        before = await read_decision(session, context.owner_id, params.earlier_id)
        after = await read_decision(session, context.owner_id, params.later_id)
        recorded_by = await authors(session, context, {before.agent_id, after.agent_id})
        return {
            **decision_changes(before, after),
            "recorded_by": {
                "earlier": recorded_by[before.agent_id],
                "later": recorded_by[after.agent_id],
            },
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "market_decision_read",
            "Read one exact immutable historical decision and its recorded broker evidence. Later prices are not substituted.",
            DecisionReference,
            read,
            True,
        ),
        Tool(
            "market_decision_record",
            "Record your BUY, SELL or CONDITIONAL_ENTRY decision with current broker evidence and rationale; WAIT remains explicit abstention. Optional detector observations assist your analysis, never choose the side. Conditional entry stores your condition, invalidation and review instruction; create a durable Task watch/wait separately before claiming monitoring. Operational failures remain separate from your decision. This never authorizes or executes a trade.",
            DecisionRequest,
            record,
            eager=eager_for("market"),
        ),
        Tool(
            "market_decision_history",
            "Retrieve immutable historical decisions/evidence on any owned account for why/what-was-known questions, each with the Agent that recorded it; never replace them with current market data.",
            DecisionHistory,
            history,
            True,
            eager=eager_for("market"),
        ),
        Tool(
            "market_decision_compare",
            "Compare two saved decisions in time order. Return only material stored differences, without hindsight or hidden reasoning.",
            DecisionCompare,
            compare,
            True,
        ),
    ]
