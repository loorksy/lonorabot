"""Reconciliation-first account observations in the existing Gateway and broker ledger."""

import asyncio
from datetime import timedelta

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import create_run
from lonora_db.schema import BrokerSessionRow, EffectReceiptRow, RunRow, TradingJournalRow
from lonora_db.threads import conversation_thread, create_thread
from lonora_db.trading_journal import persist_result
from lonora_market.health import assess_account, require_healthy
from lonora_session.idempotency import stable_id
from sqlalchemy import select, text

from .manual_activity import detect_activity


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
            {"key": f"execution:{owner_id}:{account_id}"},
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
                                TradingJournalRow.execution_mode == "live",
                            )
                            .order_by(TradingJournalRow.updated_at.desc())
                            .limit(1000)
                        )
                    )
                unresolved: list[str] = []
                for entry in entries:
                    if entry.status not in {"ambiguous", "submitted"}:
                        continue
                    if (
                        entry.status == "submitted"
                        and entry.submitted_at
                        and entry.submitted_at > now - timedelta(seconds=60)
                    ):
                        # A live fenced sender waiting for this account lock has not
                        # submitted yet. Do not make its own reservation degrade it.
                        raw_lease = entry.result.get("details", {}).get("lease")
                        lease = Lease.model_validate(raw_lease) if raw_lease else None
                        active = None
                        if lease:
                            async with db.sessions() as session:
                                active = await session.get(RunRow, lease.run_id)
                        if not (
                            active
                            and lease
                            and active.status in {"leased", "running"}
                            and active.lease_owner == lease.owner
                            and active.lease_fence == lease.fence
                            and active.lease_expires_at
                            and active.lease_expires_at > now
                        ):
                            unresolved.append(entry.operation_id)
                        continue
                    receipt = await broker.reconcile(
                        entry.operation_id, TradeRequest.model_validate(entry.request)
                    )
                    if receipt.operation_id == entry.operation_id and receipt.status in {
                        "confirmed",
                        "failed",
                    }:
                        async with db.sessions() as session, session.begin():
                            await persist_result(
                                session,
                                entry.operation_id,
                                receipt.status,
                                receipt.model_dump(mode="json"),
                            )
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
                personal = await ensure_personal_agent(session, owner_id)
                thread = await conversation_thread(session, owner_id, personal.id)
                pending_ids: list[str] = []
                for change in external:
                    key = "broker-activity:" + change.id
                    if await session.get(EffectReceiptRow, key):
                        continue
                    emit(
                        session,
                        owner_id,
                        "broker.external_activity",
                        agent_id=personal.id,
                        thread_id=thread.id,
                        payload=change.model_dump(mode="json"),
                    )
                    session.add(
                        EffectReceiptRow(
                            key=key, result={"event_id": change.id, "agent_id": personal.id}
                        )
                    )
                    pending_ids.append(change.id)
                if pending_ids and not personal.paused:
                    work = await create_thread(
                        session, owner_id, ThreadCreate(agent_id=personal.id), purpose="work"
                    )
                    # Facts only. This wake cannot grant management permission, including via descendants.
                    await create_run(
                        session,
                        owner_id,
                        RunRequest(
                            thread_id=work.id,
                            agent_id=personal.id,
                            trigger="broker_event",
                            prompt=f"Use account_activity for account_id={account_id} and inspect current account state. Explain observed changes without inventing owner intent. This is observe-only work; do not change broker state.",
                            metadata={
                                "authority": "observe_only",
                                "origin_thread_id": thread.id,
                                "account_id": account_id,
                                "broker_event_ids": pending_ids,
                                "broker_revision": revision,
                            },
                        ),
                        stable_id(account_id, "external:" + str(revision)),
                    )
        return snapshot


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
