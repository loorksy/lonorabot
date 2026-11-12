"""Reconciliation-first account observations in the existing Gateway and broker ledger."""

import asyncio

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker_activity import BrokerActivity, BrokerRecoverySnapshot
from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import create_run
from lonora_db.schema import AgentRow, BrokerSessionRow, EffectReceiptRow, TradingJournalRow
from lonora_db.threads import conversation_thread, create_thread
from lonora_market.health import assess_account, require_healthy
from lonora_session.idempotency import stable_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .manual_activity import detect_activity
from .reconciliation import observe_operation, send_lock_key, settle


async def reconcile_broker_account(
    db: Database, brokers: BrokerManager, owner_id: str, account_id: str
) -> BrokerRecoverySnapshot | None:
    async with db.sessions() as session:
        row = await BrokerSessionRepository().get(session, owner_id, account_id)
        version = row.version
        raw = row.state.get("broker_recovery")
        prior = BrokerRecoverySnapshot.model_validate(raw) if raw else None
    now = utcnow()
    revision = (prior.revision if prior else 0) + 1
    # The same account lock as execution; never hold a broker resource-row lock over IO.
    async with db.sessions() as gate, gate.begin():
        acquired = await gate.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": send_lock_key(owner_id, account_id)},
        )
        if not acquired:
            return None
        async with db.sessions() as session:
            locked_config = await BrokerSessionRepository().get(session, owner_id, account_id)
            if locked_config.version != version:
                return None
            raw = locked_config.state.get("broker_recovery")
            prior = BrokerRecoverySnapshot.model_validate(raw) if raw else None
            revision = (prior.revision if prior else 0) + 1
        try:
            async with asyncio.timeout(30):
                broker = await brokers.get(owner_id, account_id)
                account = await broker.account()
                require_healthy(
                    assess_account(
                        account, account_id=account_id, now=utcnow(), maximum_age_seconds=60
                    )
                )
                read_at = utcnow()
                positions, orders = await broker.positions(), await broker.orders()
                if len(positions) > 1000 or len(orders) > 1000:
                    raise LonoraError("broker_snapshot_limit", 409)
                async with db.sessions() as session:
                    entries = list(
                        await session.scalars(
                            select(TradingJournalRow)
                            .where(
                                TradingJournalRow.owner_id == owner_id,
                                TradingJournalRow.account_id == account_id,
                            )
                            .order_by(TradingJournalRow.updated_at.desc())
                            .limit(1000)
                        )
                    )
                unresolved: list[str] = []
                for entry in entries:
                    # Under this same account send lock a reservation has provably not
                    # been sent (reconcile_ambiguous releases an abandoned one), and a
                    # submitted operation has lost its sender: the executor persists
                    # every outcome before releasing the lock. Both are only observed.
                    if entry.status not in UNRESOLVED_STATUSES:
                        continue
                    receipt = await observe_operation(broker, entry, (positions, orders, read_at))
                    if receipt is not None:
                        await settle(db, entry.operation_id, receipt)
                        entry.status, entry.result = receipt.status, receipt.model_dump(mode="json")
                    else:
                        unresolved.append(entry.operation_id)
                changes = detect_activity(
                    account_id, prior, positions, orders, entries, revision=revision, now=now
                )
                external = [change for change in changes if change.origin == "external"]
                snapshot = BrokerRecoverySnapshot(
                    status="degraded" if unresolved else "connected",
                    reason_code="broker_reconciliation_pending"
                    if unresolved
                    else "broker_reconciled",
                    since=prior.since
                    if prior and prior.status == ("degraded" if unresolved else "connected")
                    else now,
                    observed_at=now,
                    last_success_at=now,
                    reconciled_at=None if unresolved else now,
                    revision=revision,
                    external_revision=(prior.external_revision if prior else 0) + bool(external),
                    unresolved_operations=unresolved,
                    account=account,
                    positions=positions,
                    orders=orders,
                )
        except (Exception, TimeoutError) as error:
            snapshot = BrokerRecoverySnapshot(
                status="disconnected",
                reason_code=error.code
                if isinstance(error, LonoraError)
                else "broker_recovery_unavailable",
                since=prior.since if prior and prior.status == "disconnected" else now,
                observed_at=now,
                last_success_at=prior.last_success_at if prior else None,
                revision=revision,
                external_revision=prior.external_revision if prior else 0,
                positions=prior.positions if prior else [],
                orders=prior.orders if prior else [],
                account=prior.account if prior else None,
                unresolved_operations=prior.unresolved_operations if prior else [],
            )
            external = []
        async with db.sessions() as session, session.begin():
            saved = await BrokerSessionRepository().get(session, owner_id, account_id, lock=True)
            if saved.version != version or not saved.payload.get("enabled"):
                return None
            # Cross-process observations use the account lock; configuration version fences stale IO.
            saved.state = {**saved.state, "broker_recovery": snapshot.model_dump(mode="json")}
            if prior is None or (prior.status, prior.reason_code) != (
                snapshot.status,
                snapshot.reason_code,
            ):
                emit(
                    session,
                    owner_id,
                    "broker.recovered" if snapshot.status == "connected" else "broker.degraded",
                    payload={
                        "account_id": account_id,
                        "status": snapshot.status,
                        "reason_code": snapshot.reason_code,
                        "previous_status": prior.status if prior else None,
                        "transition_id": snapshot.status + ":" + snapshot.since.isoformat(),
                    },
                )
            if external:
                await wake_for_activity(session, owner_id, account_id, revision, external)
        return snapshot


async def wake_for_activity(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    revision: int,
    external: list[BrokerActivity],
) -> None:
    """Wake the Agent responsible for each external broker change, once per change.

    A change on a ticket the journal attributes to an Agent (a stop-loss or take-profit
    hit, a manual close of its position) wakes that Agent with its normal authority:
    its grant, the account limits and pauses still decide at the executor. A paused
    Agent is woken too, for its own positions and orders only, and may only reduce risk
    (4.7.1). Unattributed activity is the owner's own and wakes the Personal Agent with
    no financial effects, as does activity of an Agent that no longer exists; a paused
    Personal Agent is not woken for it.
    """
    personal = await ensure_personal_agent(session, owner_id)
    groups: dict[tuple[str, bool], list[str]] = {}
    agents: dict[str, AgentRow] = {personal.id: personal}
    for change in external:
        key = "broker-activity:" + change.id
        if await session.get(EffectReceiptRow, key):
            continue
        responsible = await session.get(AgentRow, change.agent_id) if change.agent_id else None
        attributed = bool(
            responsible and responsible.owner_id == owner_id and responsible.role != "delegated"
        )
        agent = responsible if attributed and responsible else personal
        agents[agent.id] = agent
        thread = await conversation_thread(session, owner_id, agent.id)
        emit(
            session,
            owner_id,
            "broker.external_activity",
            agent_id=agent.id,
            thread_id=thread.id,
            payload=change.model_dump(mode="json"),
        )
        session.add(EffectReceiptRow(key=key, result={"event_id": change.id, "agent_id": agent.id}))
        groups.setdefault((agent.id, attributed), []).append(change.id)
    for (agent_id, attributed), pending_ids in groups.items():
        agent = agents[agent_id]
        if agent.paused and not attributed:
            continue
        thread = await conversation_thread(session, owner_id, agent.id)
        work = await create_thread(
            session, owner_id, ThreadCreate(agent_id=agent.id), purpose="work"
        )
        metadata = {
            "origin_thread_id": thread.id,
            "account_id": account_id,
            "broker_event_ids": pending_ids,
            "broker_revision": revision,
        }
        if attributed:
            prompt = (
                f"Broker activity on positions or orders you opened or manage on account_id="
                f"{account_id}. Use account_activity and current account state to reassess them "
                "and decide what to do next. Your normal authority applies; your grant, account "
                "limits and pauses decide at execution. Never resend an uncertain operation."
            )
            if agent.paused:
                prompt += (
                    " You are paused: only risk-reducing requests are sent (a full or partial "
                    "close, cancelling a pending order, adding a stop loss, or moving a stop "
                    "loss toward the market); take no new work."
                )
            identifier = stable_id(account_id, f"external:{revision}:{agent.id}")
        else:
            # Facts only. No financial effects from this wake, its helpers, peer runs or
            # the Tasks it starts; watches it sets fire later as the Agent's own work.
            prompt = (
                f"Use account_activity for account_id={account_id} and inspect current account "
                "state. Explain observed changes without inventing owner intent. This wake has "
                "no financial effects: do not change broker state; you may save findings, adjust "
                "watches, tell colleagues or notify the owner."
            )
            metadata["authority"] = "observe_only"
            identifier = stable_id(account_id, "external:" + str(revision))
        await create_run(
            session,
            owner_id,
            RunRequest(
                thread_id=work.id,
                agent_id=agent.id,
                trigger="broker_event",
                prompt=prompt,
                metadata=metadata,
            ),
            identifier,
        )


async def maintenance_account_recovery(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    async with db.sessions() as session:
        ids = list(
            await session.scalars(
                select(BrokerSessionRow.id)
                .where(
                    BrokerSessionRow.owner_id == owner_id,
                    BrokerSessionRow.payload["enabled"].as_boolean().is_(True),
                )
                .order_by(
                    BrokerSessionRow.state["broker_recovery"]["observed_at"]
                    .as_string()
                    .asc()
                    .nulls_first(),
                    BrokerSessionRow.id,
                )
                .limit(32)
            )
        )
    results = await asyncio.gather(
        *(reconcile_broker_account(db, brokers, owner_id, identifier) for identifier in ids),
        return_exceptions=True,
    )
    return sum(isinstance(result, BrokerRecoverySnapshot) for result in results)
