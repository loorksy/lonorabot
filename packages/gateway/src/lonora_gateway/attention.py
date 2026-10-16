"""Meaningful runtime transitions become one audited owner attention projection."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.attention import AttentionClassification
from lonora_contracts.domain import utcnow
from lonora_contracts.market_watch import Watch
from lonora_contracts.trading import TradingControl
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.attention import attention_data, decide_attention, policy, set_cursor
from lonora_db.client import Database
from lonora_db.events import PUBLIC_CURSOR, emit, publish_committed
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AttentionRow,
    BrokerSessionRow,
    CollaborationSessionRow,
    EffectReceiptRow,
    EventRow,
    MarketWatchRow,
    SettingRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
    TradingGoalRow,
    TradingOpportunityRow,
)
from lonora_db.threads import conversation_thread
from lonora_db.transactions import SettingsRepository, owned_agent
from lonora_market.watchers import observe
from lonora_trading.opportunities import evidence_state
from sqlalchemy import select


async def validate_watch(db: Database, brokers: BrokerManager, row: MarketWatchRow) -> datetime:
    config = Watch.model_validate(row.payload)
    now = utcnow()
    expiry = row.state.get("confirmation_valid_until")
    if (
        not config.enabled
        or row.state.get("lifecycle") != "confirmed"
        or row.state.get("evaluation_status") == "suspended_health"
        or row.state.get("health", {}).get("state", "healthy") != "healthy"
        or (config.expires_at and config.expires_at <= now)
        or (expiry and datetime.fromisoformat(expiry) <= now)
    ):
        raise LonoraError("attention_setup_not_current", 409)
    async with asyncio.timeout(5):
        current, _, _ = await observe(db, brokers, row, config)
    if config.kind == "dynamic":
        valid = current == 1
    elif config.condition in {"changed", "closed", "opened", "due"}:
        valid = current == Decimal(str(row.state.get("last_value", "NaN")))
    else:
        valid = condition_met(
            {"cross_above": "above", "cross_below": "below"}.get(
                config.condition, config.condition
            ),
            config.level,
            current,
            None,
        )
    if not valid:
        raise LonoraError("attention_setup_not_current", 409)
    from lonora_market.health import assess_quote, require_healthy

    broker = await brokers.get(row.owner_id, config.account_id)
    async with asyncio.timeout(5):
        quote = await broker.quote(config.symbol)
    require_healthy(
        assess_quote(
            quote,
            account_id=config.account_id,
            symbol=config.symbol,
            now=utcnow(),
            maximum_age_seconds=30,
        )
    )
    deadlines = [quote.observed_at + timedelta(seconds=30)]
    if expiry:
        deadlines.append(datetime.fromisoformat(expiry))
    if config.expires_at:
        deadlines.append(config.expires_at)
    return min(deadlines)


async def candidate(
    db: Database,
    brokers: BrokerManager,
    event: EventRow,
) -> tuple[AttentionClassification, str, str, dict[str, Any], str]:
    classification = classify_attention(event.kind, event.payload)
    parameters: dict[str, Any] = {"execution_authorized": False}
    scope = event.kind.split(".")[0] + ":" + classification.resource_id
    async with db.sessions() as session, session.begin():
        personal = await ensure_personal_agent(session, event.owner_id)
        agent_id, thread_id = event.agent_id or personal.id, event.thread_id
        identifier = classification.resource_id
        resource: Any = None
        if event.kind.startswith("broker.") or event.kind == "trading.controls_updated":
            agent_id, thread_id = personal.id, None
        if event.kind == "trading.controls_updated":
            current = TradingControl.model_validate(
                await SettingsRepository().get(session, "trading_control")
            )
            if classification.code == "emergency_stop" and not current.emergency_stop:
                raise LonoraError("attention_superseded_state", 409)
        elif event.kind.startswith("broker."):
            account_id = str(event.payload.get("account_id", ""))
            source = await session.get(BrokerSessionRow, account_id)
            if source is None or source.owner_id != event.owner_id:
                raise LonoraError("attention_source_unavailable", 404)
            parameters["account_id"] = account_id
            scope = "account:" + account_id
            if event.kind != "broker.external_activity":
                current = source.state.get("broker_recovery", {})
                if current.get("status") != event.payload.get("status"):
                    raise LonoraError("attention_superseded_state", 409)
                if (
                    event.payload.get("transition_id")
                    and current.get("since")
                    and event.payload["transition_id"]
                    != str(current.get("status"))
                    + ":"
                    + datetime.fromisoformat(current["since"]).isoformat()
                ):
                    raise LonoraError("attention_superseded_state", 409)
                if classification.code == "broker_degraded" and (
                    current.get("positions") or current.get("unresolved_operations")
                ):
                    classification.importance = "critical"
            else:
                parameters["symbol"] = event.payload.get("symbol")
                scope += ":activity:" + str(event.payload.get("symbol", ""))
        elif event.kind == "trading.approval.updated":
            resource = await session.get(TradeApprovalRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                agent_id, thread_id = resource.agent_id, resource.thread_id
                if resource.status != event.payload.get("status"):
                    raise LonoraError("attention_superseded_state", 409)
                parameters.update(
                    approval_id=resource.id,
                    symbol=resource.requests[0].get("symbol") if resource.requests else None,
                )
        elif event.kind.startswith("watch."):
            resource = await session.get(MarketWatchRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                if resource.payload.get("kind", "price") not in {
                    "price",
                    "indicator",
                    "dynamic",
                } and classification.code in {"setup_confirmed", "thesis_invalidated"}:
                    classification.importance, classification.code = (
                        "important_change",
                        "watch_condition_met",
                    )
                if event.payload.get("state") and event.payload["state"] != resource.state.get(
                    "lifecycle"
                ):
                    raise LonoraError("attention_superseded_state", 409)
                if (
                    event.kind == "watch.suspended_health"
                    and resource.state.get("evaluation_status") != "suspended_health"
                ):
                    raise LonoraError("attention_superseded_state", 409)
                if (
                    event.kind == "watch.resumed_health"
                    and resource.state.get("evaluation_status") == "suspended_health"
                ):
                    raise LonoraError("attention_superseded_state", 409)
                agent_id, thread_id = resource.agent_id, resource.thread_id
                parameters.update(
                    account_id=resource.payload.get("account_id"),
                    symbol=resource.payload.get("symbol"),
                    watch_id=resource.id,
                )
                scope = "setup:" + resource.id
        elif event.kind == "opportunity.transition":
            resource = await session.get(TradingOpportunityRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                agent_id, thread_id = resource.agent_id, resource.thread_id
                parameters.update(
                    account_id=resource.account_id,
                    symbol=resource.symbol,
                    opportunity_id=resource.id,
                )
                scope = "setup:" + str(resource.payload.get("watch_id") or resource.id)
                if resource.status != event.payload.get(
                    "status"
                ) or resource.version != event.payload.get("version"):
                    raise LonoraError("attention_superseded_state", 409)
                if classification.importance == "opportunity":
                    codes, facts = await evidence_state(session, resource, utcnow())
                    if codes:
                        raise LonoraError("attention_evidence_stale", 409)
                    deadlines = [
                        datetime.fromisoformat(value["last_good_at"]) + timedelta(seconds=30)
                        for value in facts["health_assessments"]
                        if value.get("resource") == "quote" and value.get("last_good_at")
                    ]
                    if deadlines:
                        parameters["valid_until"] = min(deadlines).isoformat()
        elif event.kind.startswith("collaboration."):
            resource = await session.get(CollaborationSessionRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                agent_id, thread_id = resource.agent_id, resource.thread_id
                if (
                    classification.code == "collaboration_completed"
                    and resource.state.get("status") != "completed"
                ):
                    raise LonoraError("attention_superseded_state", 409)
        elif event.kind.startswith("task."):
            resource = await session.get(TicketRow, identifier)
            if resource and resource.owner_id == event.owner_id and resource.state.get("task"):
                state = resource.state["task"]
                parameters["task_id"] = resource.id
                if event.payload.get("version") and event.payload["version"] != resource.version:
                    raise LonoraError("attention_superseded_state", 409)
                failure: dict[str, Any] = state.get("failure") or {}
                if event.kind == "task.failed" and event.payload.get("attempt") != failure.get(
                    "attempt"
                ):
                    raise LonoraError("attention_superseded_state", 409)
                agent_id, thread_id = resource.agent_id, state["origin_thread_id"]
                if classification.code == "task_review" and state["status"] != "failed":
                    raise LonoraError("attention_superseded_state", 409)
                if classification.code == "task_completed" and state["status"] != "completed":
                    raise LonoraError("attention_superseded_state", 409)
        elif event.kind == "goals.updated":
            resource = await session.get(TradingGoalRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                agent_id, thread_id = resource.agent_id, resource.thread_id
                if resource.version != event.payload.get("version"):
                    raise LonoraError("attention_superseded_state", 409)
        if not (event.kind.startswith("broker.") or event.kind == "trading.controls_updated") and (
            resource is None or resource.owner_id != event.owner_id
        ):
            raise LonoraError("attention_source_unavailable", 404)
        if not agent_id:
            raise LonoraError("attention_source_unavailable", 404)
        await owned_agent(session, event.owner_id, agent_id)
        thread = await session.get(ThreadRow, thread_id) if thread_id else None
        if thread is None or thread.owner_id != event.owner_id or thread.purpose != "conversation":
            thread = await conversation_thread(session, event.owner_id, agent_id)
        thread_id = thread.id
        if thread.group_id:
            parameters["group_id"] = thread.group_id
    if isinstance(resource, MarketWatchRow) and classification.importance == "opportunity":
        parameters["valid_until"] = (await validate_watch(db, brokers, resource)).isoformat()
    if isinstance(resource, TradingOpportunityRow) and classification.importance == "opportunity":
        broker = await brokers.get(event.owner_id, resource.account_id)
        from lonora_market.health import assess_quote, require_healthy

        async with asyncio.timeout(5):
            quote = await broker.quote(resource.symbol)
        require_healthy(
            assess_quote(
                quote,
                account_id=resource.account_id,
                symbol=resource.symbol,
                now=utcnow(),
                maximum_age_seconds=30,
            )
        )
        parameters["valid_until"] = min(
            quote.observed_at + timedelta(seconds=30),
            resource.expires_at,
            datetime.fromisoformat(parameters["valid_until"])
            if parameters.get("valid_until")
            else resource.expires_at,
        ).isoformat()
    return classification, agent_id, thread_id, parameters, scope


async def attention_tick(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    async with db.sessions() as session:
        await publish_committed(session)
        counter = await session.get(SettingRow, "attention-cursor:" + owner_id)
        cursor = int(counter.payload.get("cursor", 0)) if counter else 0
        events = list(
            await session.scalars(
                select(EventRow)
                .where(
                    EventRow.owner_id == owner_id,
                    EventRow.kind.in_(ATTENTION_KINDS),
                    EventRow.payload[PUBLIC_CURSOR].as_integer() > cursor,
                )
                .order_by(EventRow.payload[PUBLIC_CURSOR].as_integer())
                .limit(50)
            )
        )
    # No market IO is allowed to delay a critical transition behind a slow quote lookup.
    events.sort(
        key=lambda event: (
            0
            if classify_attention(event.kind, event.payload).importance
            in {"critical", "action_required"}
            or event.kind.startswith("broker.")
            else 1
        )
    )
    for event in events:
        async with db.sessions() as session:
            if await session.get(
                EffectReceiptRow, "attention-source:" + owner_id + ":" + str(event.cursor)
            ):
                continue
        suppression: str | None = None
        try:
            classification, agent_id, thread_id, parameters, scope = await candidate(
                db, brokers, event
            )
        except (LonoraError, TimeoutError) as error:
            suppression = (
                error.code if isinstance(error, LonoraError) else "attention_revalidation_timeout"
            )
            classification = classify_attention(event.kind, event.payload)
            async with db.sessions() as session, session.begin():
                personal = await ensure_personal_agent(session, owner_id)
                thread = await conversation_thread(session, owner_id, personal.id)
                agent_id, thread_id, parameters, scope = (
                    personal.id,
                    thread.id,
                    {},
                    "suppressed:" + classification.resource_id,
                )
        async with db.sessions() as session, session.begin():
            await decide_attention(
                session,
                event,
                classification,
                agent_id=agent_id,
                thread_id=thread_id,
                parameters=parameters,
                coalesce_scope=scope,
                suppression_code=suppression,
            )
        if classification.importance in {"critical", "action_required"}:
            await ready_attention(db, brokers, owner_id)
    if events:
        async with db.sessions() as session, session.begin():
            await set_cursor(
                session, owner_id, max(int(event.payload[PUBLIC_CURSOR]) for event in events)
            )
    return await ready_attention(db, brokers, owner_id)


async def ready_attention(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    async with db.sessions() as session:
        rows = list(
            await session.scalars(
                select(AttentionRow)
                .where(
                    AttentionRow.owner_id == owner_id,
                    AttentionRow.status == "pending",
                    AttentionRow.due_at <= utcnow(),
                )
                .order_by(AttentionRow.due_at)
                .limit(50)
            )
        )
    count = 0
    for original in rows:
        suppression = None
        async with db.sessions() as session:
            settings = await policy(session, owner_id)
        if original.importance == "opportunity" and not settings.opportunities:
            suppression = "owner_opportunity_preference"
        if original.importance == "informational" and not settings.informational:
            suppression = "owner_informational_preference"
        if original.importance == "opportunity" and suppression is None:
            async with db.sessions() as session:
                source = await session.get(EventRow, original.source_events[-1])
            if source:
                try:
                    await candidate(db, brokers, source)
                except (LonoraError, TimeoutError) as error:
                    suppression = (
                        error.code
                        if isinstance(error, LonoraError)
                        else "attention_revalidation_timeout"
                    )
            else:
                suppression = "attention_source_unavailable"
        async with db.sessions() as session, session.begin():
            row = await session.get(
                AttentionRow, original.id, with_for_update=True, populate_existing=True
            )
            if row is None or row.status != "pending" or row.version != original.version:
                continue
            row.status, row.version, row.updated_at = (
                "suppressed" if suppression else "ready",
                row.version + 1,
                utcnow(),
            )
            if suppression:
                row.parameters = {**row.parameters, "suppression_code": suppression}
            emit(
                session,
                owner_id,
                "attention.updated",
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                payload=attention_data(row),
            )
            if not suppression:
                emit(
                    session,
                    owner_id,
                    "attention.ready",
                    agent_id=row.agent_id,
                    thread_id=row.thread_id,
                    payload=attention_data(row),
                )
                count += 1
    return count
