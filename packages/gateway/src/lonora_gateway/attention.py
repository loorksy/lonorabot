"""Meaningful runtime transitions become one audited owner attention projection."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.attention import AttentionClassification
from lonora_contracts.domain import utcnow
from lonora_contracts.market_watch import Watch
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.attention import (
    decide_attention,
    follow_broker_health,
    mandate_already_shown,
    policy,
    publish_ready,
    raise_system_attention,
    set_cursor,
    withdraw_ended,
)
from lonora_db.client import Database
from lonora_db.events import PUBLIC_CURSOR, publish_committed
from lonora_db.item_failures import ItemGuard, blocked, due_retries
from lonora_db.owner_actions import live_status
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    CollaborationSessionRow,
    EffectReceiptRow,
    EventRow,
    MarketWatchRow,
    OwnerActionRow,
    RunRow,
    SettingRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
    TradingJournalRow,
    TradingOpportunityRow,
)
from lonora_db.system_alerts import wake_for_alerts
from lonora_db.threads import conversation_thread
from lonora_db.transactions import owned_agent
from lonora_market.watchers import observe
from lonora_trading.opportunities import evidence_state
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .owner_cards import CARD_EVENTS, follow_event


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
        current, _, metadata = await observe(db, brokers, row, config)
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
    observation_expiry = metadata.get("observation", {}).get("valid_until")
    if observation_expiry:
        deadlines.append(datetime.fromisoformat(observation_expiry))
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
        responsible = (
            event.kind == "broker.external_activity"
            and bool(event.payload.get("agent_id"))
            and event.agent_id == event.payload.get("agent_id")
        )
        if responsible:
            # Activity on an Agent's own positions reaches the owner in that Agent's chat.
            agent_id = str(event.agent_id)
        elif event.kind.startswith("broker."):
            agent_id, thread_id = personal.id, None
        if event.kind.startswith("broker."):
            account_id = str(event.payload.get("account_id", ""))
            source = await session.get(BrokerSessionRow, account_id)
            if source is None or source.owner_id != event.owner_id:
                raise LonoraError("attention_source_unavailable", 404)
            parameters["account_id"] = account_id
            parameters["symbol"] = event.payload.get("symbol")
            scope = "account:" + account_id + ":activity:" + str(event.payload.get("symbol", ""))
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
        elif event.kind == "trading.operation_updated":
            resource = await session.get(TradingJournalRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                # An older transition never withdraws or repeats a newer one.
                if resource.status != event.payload.get("status"):
                    raise LonoraError("attention_superseded_state", 409)
                agent = await session.get(AgentRow, event.agent_id) if event.agent_id else None
                if agent is None or agent.owner_id != event.owner_id:
                    # The owner's own order, or its agent is gone: Lonora's conversation.
                    agent_id, thread_id = personal.id, None
                parameters.update(
                    operation_id=resource.operation_id,
                    account_id=resource.account_id,
                    symbol=resource.request.get("symbol"),
                )
                scope = "operation:" + resource.operation_id
        elif event.kind == "owner_action.updated":
            resource = await session.get(OwnerActionRow, identifier)
            if resource and resource.owner_id == event.owner_id:
                # An older transition never withdraws or repeats a newer one.
                if live_status(resource) != event.payload.get("status"):
                    raise LonoraError("attention_superseded_state", 409)
                agent_id, thread_id = resource.agent_id, resource.thread_id
                parameters["owner_action_id"] = resource.id
                scope = "owner_action:" + resource.id
                if classification.code == "mandate_proposed" and await mandate_already_shown(
                    session, resource
                ):
                    # One item per agent's mode: the owner already has a Mandate card
                    # for this agent in front of them, and one tap answers both.
                    raise LonoraError("attention_card_already_shown", 409)
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
                    deadlines.extend(
                        datetime.fromisoformat(value["valid_until"])
                        for value in facts.get("relationships", [])
                        if value.get("valid_until")
                    )
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
                # The Task's own work thread holds its questions and reports; the
                # item itself still opens the owner's conversation with the agent.
                parameters["work_thread_id"] = resource.thread_id
                if event.payload.get("version") and event.payload["version"] != resource.version:
                    raise LonoraError("attention_superseded_state", 409)
                failure: dict[str, Any] = state.get("failure") or {}
                if event.kind == "task.failed" and event.payload.get("attempt") != failure.get(
                    "attempt"
                ):
                    raise LonoraError("attention_superseded_state", 409)
                agent_id, thread_id = resource.agent_id, state["origin_thread_id"]
                if classification.code == "task_review" and not (
                    state["status"] == "failed"
                    or (
                        state["status"] == "waiting"
                        and state.get("waiting_reason") == "owner_attention"
                    )
                ):
                    raise LonoraError("attention_superseded_state", 409)
                if classification.code == "task_completed" and state["status"] != "completed":
                    raise LonoraError("attention_superseded_state", 409)
                if classification.code == "task_degraded":
                    # Only while the same Run is still retrying through the outage.
                    run = await session.get(RunRow, str(event.payload.get("run_id") or ""))
                    recovery: dict[str, Any] = (
                        run.execution_state.get("model_recovery") or {} if run else {}
                    )
                    if (
                        state["status"] in {"paused", "completed", "failed", "cancelled"}
                        or run is None
                        or run.id != resource.payload.get("run_id")
                        or not recovery.get("failures")
                    ):
                        raise LonoraError("attention_superseded_state", 409)
        if not event.kind.startswith("broker.") and (
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


async def project_event(
    db: Database, brokers: BrokerManager, owner_id: str, event: EventRow
) -> None:
    async with db.sessions() as session:
        if await session.get(
            EffectReceiptRow, "attention-source:" + owner_id + ":" + str(event.cursor)
        ):
            return
    if event.kind in CARD_EVENTS:
        # Owner action cards first: a failure retries this event before its notification.
        async with db.sessions() as session, session.begin():
            await follow_event(session, event)
    suppression: str | None = None
    try:
        classification, agent_id, thread_id, parameters, scope = await candidate(db, brokers, event)
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


URGENT = frozenset({"critical", "action_required"})


async def quarantine_event(session: AsyncSession, item_id: str) -> bool:
    """Quarantine: an event that keeps failing is recorded as decided and never re-read.

    A critical or action-required event still reaches the owner under its own code
    (without the details its failed projection would have added): a projection bug
    must never cost the owner an approval alert.
    """
    event = await session.get(EventRow, int(item_id))
    if event is None:
        return True
    key = "attention-source:" + event.owner_id + ":" + str(event.cursor)
    classification = classify_attention(event.kind, event.payload)
    if classification.importance in URGENT:
        await raise_system_attention(
            session,
            event.owner_id,
            classification.code,
            "event:" + str(event.cursor),
            {"reason_code": "attention_projection_failed"},
            agent_id=event.agent_id,
            thread_id=event.thread_id,
            importance=classification.importance,
        )
    if await session.get(EffectReceiptRow, key) is None:
        session.add(
            EffectReceiptRow(
                key=key,
                result={
                    "source_event": event.cursor,
                    "status": "suppressed",
                    "reason_code": "attention_projection_failed",
                },
            )
        )
    return True


async def suppress_item(session: AsyncSession, item_id: str) -> bool:
    """Quarantine: a notification that cannot be readied is not retried forever.

    A critical or action-required one is delivered as it is rather than lost; any
    other is suppressed.
    """
    row = await session.get(AttentionRow, item_id, with_for_update=True)
    if row is not None and row.status == "pending":
        urgent = row.importance in URGENT
        publish_ready(session, row, None if urgent else "attention_projection_failed")
    return True


async def attention_tick(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    # Broker health first (9.4): it reads stored state only, never broker IO. Each step
    # is isolated like an event, so a failure there never holds back the projection.
    health = ItemGuard(db, "attention_health", quarantine_after=None)
    # Withdraw first, so a problem that changed is replaced in the same tick.
    steps = {
        "withdraw:" + owner_id: withdraw_ended,
        "broker_health:" + owner_id: follow_broker_health,
    }
    await health.prepare(steps)
    for item_id, step in steps.items():

        async def follow(step: Any = step) -> None:
            async with db.sessions() as session, session.begin():
                await step(session, owner_id)

        await health.run(item_id, owner_id, follow)
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
    # Each event is isolated: one that raises or hangs past its own time limit is
    # recorded in the failure ledger and retried there, so the cursor still advances past
    # it and later events (critical broker alerts included) are never stuck behind it.
    guard = ItemGuard(db, "attention_event", quarantine=quarantine_event)
    await guard.prepare(str(event.cursor) for event in events)
    order = sorted(int(event.payload[PUBLIC_CURSOR]) for event in events)
    handled: set[int] = set()
    written = cursor

    async def advance(position: int) -> None:
        # Per event, over the handled prefix only (critical events are handled first),
        # so even a cancelled iteration keeps every event it already decided.
        nonlocal written
        handled.add(position)
        target = written
        for value in order:
            if value <= written:
                continue
            if value not in handled:
                break
            target = value
        if target > written:
            async with db.sessions() as session, session.begin():
                await set_cursor(session, owner_id, target)
            written = target

    for event in events:
        if str(event.cursor) not in guard.failing:

            async def project(event: EventRow = event) -> None:
                await project_event(db, brokers, owner_id, event)

            await guard.run(str(event.cursor), owner_id, project)
        await advance(int(event.payload[PUBLIC_CURSOR]))
    async with db.sessions() as session:
        retries = [
            event
            for failure in await due_retries(session, "attention_event", owner_id)
            if (event := await session.get(EventRow, int(failure.item_id))) is not None
        ]
    retry = ItemGuard(db, "attention_event", quarantine=quarantine_event)
    await retry.prepare(str(event.cursor) for event in retries)
    for event in retries:

        async def again(event: EventRow = event) -> None:
            await project_event(db, brokers, owner_id, event)

        await retry.run(str(event.cursor), owner_id, again)
    readied = await ready_attention(db, brokers, owner_id)
    # Lonora receives the system alerts (3.1.5): isolated like the health steps.
    alerts = ItemGuard(db, "attention_health", quarantine_after=None)
    await alerts.prepare(["wake:" + owner_id])

    async def wake() -> None:
        async with db.sessions() as session, session.begin():
            await wake_for_alerts(session, owner_id)

    await alerts.run("wake:" + owner_id, owner_id, wake)
    return readied


async def ready_attention(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    async with db.sessions() as session:
        rows = list(
            await session.scalars(
                select(AttentionRow)
                .where(
                    AttentionRow.owner_id == owner_id,
                    AttentionRow.status == "pending",
                    AttentionRow.due_at <= utcnow(),
                    ~blocked("attention_item", AttentionRow.id),
                )
                .order_by(AttentionRow.due_at)
                .limit(50)
            )
        )
    guard = ItemGuard(db, "attention_item", quarantine=suppress_item)
    await guard.prepare(row.id for row in rows)
    count = 0
    for original in rows:

        async def ready(original: AttentionRow = original) -> bool:
            return await ready_one(db, brokers, owner_id, original)

        count += int(bool(await guard.run(original.id, owner_id, ready)))
    return count


async def ready_one(
    db: Database, brokers: BrokerManager, owner_id: str, original: AttentionRow
) -> bool:
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
            return False
        return publish_ready(session, row, suppression)
