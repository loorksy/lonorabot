"""Reliability first: isolated maintenance, a deterministic watchdog, durable records, drain.

Runs on the shared ``task_db`` fixture (a disposable PostgreSQL schema when
``LONORA_TASK_TEST_DATABASE_URL`` is set, otherwise in-memory SQLite). Cascade checks need
PostgreSQL foreign keys and are skipped on SQLite.
"""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import lonora_agent.executor as executor
import lonora_db.item_failures as item_failures
import lonora_db.routines as routines
import lonora_gateway.attention as attention
import lonora_gateway.service as service
import lonora_market.watchers as watchers
import pytest
import yaml
from lonora_adapter_kit.types import ModelReply
from lonora_adapters.brokers.base import BrokerManager
from lonora_automation.runner import dispatch_routines
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.attention import ATTENTION_KINDS
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.agent_permissions import permission_state
from lonora_db.agent_state import agent_live_state
from lonora_db.cancellation import cancel_run
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.item_failures import QUARANTINE_AFTER, ItemGuard
from lonora_db.obligations import prepare_delete
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import MAX_RUN_RECOVERIES, claim_next, create_run, release_leases, require_lease
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    EffectReceiptRow,
    EventRow,
    GatewayRow,
    ItemFailureRow,
    MarketWatchRow,
    MessageRow,
    RoutineRow,
    RunRow,
    SettingRow,
    SuperBotRequestRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_gateway.health import gateway_health
from lonora_gateway.liveness import Liveness, StepLiveness, StepSpec, supervise_step
from lonora_gateway.runtime import OwnerServices
from lonora_gateway.shutdown import drain
from lonora_gateway.watchdog import Watchdog
from lonora_tools.base import Tool
from lonora_tools.context import RunDrain, ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import (
    Arguments,
    Script,
    calls,
    context_for,
    conversation_run,
    results,
    saved_run,
    seeded,
)

Fixture = tuple[Database, str, str, str]
POSTGRES = bool(os.environ.get("LONORA_TASK_TEST_DATABASE_URL"))
NO_BROKERS = cast(BrokerManager, None)


async def system_items(db: Database, owner: str, code: str) -> list[AttentionRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(AttentionRow).where(
                    AttentionRow.owner_id == owner, AttentionRow.code == code
                )
            )
        )


async def failure(db: Database, kind: str, item_id: str) -> ItemFailureRow | None:
    async with db.sessions() as session:
        return await session.get(ItemFailureRow, (kind, item_id), populate_existing=True)


async def expire_backoff(db: Database, kind: str) -> None:
    async with db.sessions() as session, session.begin():
        await session.execute(
            update(ItemFailureRow)
            .where(ItemFailureRow.kind == kind)
            .values(next_attempt_at=utcnow() - timedelta(seconds=1))
        )


@pytest.mark.asyncio
async def test_poison_routine_backs_off_and_is_quarantined_while_others_fire(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        good = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="good",
            interval_seconds=60,
            next_run_at=utcnow() - timedelta(seconds=5),
        )
        bad = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="bad",
            interval_seconds=60,
            next_run_at=utcnow() - timedelta(seconds=10),
        )
        session.add_all([good, bad])
    real = routines.create_run

    async def poisoned(
        session: Any, owner_id: str, request: RunRequest, run_id: str | None = None
    ) -> RunRow:
        if request.prompt == "bad":
            raise KeyError("poison")
        return await real(session, owner_id, request, run_id)

    monkeypatch.setattr(routines, "create_run", poisoned)
    # The poison routine is due first; before isolation it rolled back the whole batch.
    assert await dispatch_routines(db) == 1
    recorded = await failure(db, "routine", bad.id)
    assert recorded and recorded.failures == 1 and recorded.code == "unexpected_key_error"
    async with db.sessions() as session:
        fired = list(await session.scalars(select(RunRow).where(RunRow.trigger == "routine")))
    assert [run.model_metadata["routine_id"] for run in fired] == [good.id]
    # Backing off, it no longer takes a slot in the next batch.
    assert await dispatch_routines(db) == 0
    assert (await failure(db, "routine", bad.id)).failures == 1  # type: ignore[union-attr]
    for _ in range(QUARANTINE_AFTER - 1):
        await expire_backoff(db, "routine")
        await dispatch_routines(db)
    async with db.sessions() as session:
        quarantined = await session.get(RoutineRow, bad.id)
        assert quarantined and quarantined.enabled is False
    # Disabled in its own record, so the ledger row is gone: re-enabling starts fresh.
    assert await failure(db, "routine", bad.id) is None
    items = await system_items(db, owner, "maintenance_item_quarantined")
    assert len(items) == 1 and items[0].status == "ready"
    assert items[0].parameters["item_kind"] == "routine"
    assert items[0].parameters["execution_authorized"] is False


@pytest.mark.asyncio
async def test_a_failing_step_never_stops_reconciliation_and_liveness_is_persisted(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db, owner, _, _ = task_db
    calls = {"reconcile": 0}

    async def broken(_: Database) -> int:
        raise RuntimeError("poison routine")

    async def reconcile(_: Database, __: BrokerManager) -> int:
        calls["reconcile"] += 1
        return 0

    monkeypatch.setattr(service, "dispatch_routines", broken)
    monkeypatch.setattr(service, "reconcile_ambiguous", reconcile)
    monkeypatch.setattr(
        service,
        "STEPS",
        (
            StepSpec("routines", 0.02, 1),
            StepSpec("reconcile", 0.02, 1),
            StepSpec("heartbeat", 0.05, 1),
        ),
    )
    gateway = service.Gateway(db, "unused-key", tmp_path, maximum_subagents=0)

    async def idle(lane: str | None = None, name: str = "worker") -> None:
        await gateway.stop.wait()

    monkeypatch.setattr(gateway, "worker_loop", idle)
    gateway.services[owner] = cast(OwnerServices, SimpleNamespace(brokers=None, owner_id=owner))
    tasks = gateway.start()
    await asyncio.sleep(0.5)
    gateway.request_stop()
    await drain(tasks, 2)
    assert calls["reconcile"] >= 5
    failed = gateway.liveness.steps["routines"]
    assert failed.failures >= 1 and failed.last_error == "unexpected_runtime_error"
    assert gateway.liveness.steps["reconcile"].succeeded_at is not None
    async with db.sessions() as session:
        row = await session.get(GatewayRow, gateway.identity)
    assert row is not None and row.liveness["steps"]["routines"]["failures"] >= 1
    assert row.liveness["steps"]["reconcile"]["failures"] == 0


@pytest.mark.asyncio
async def test_a_hung_iteration_times_out_and_the_step_keeps_running() -> None:
    stop, liveness, started = asyncio.Event(), Liveness(), [0]

    async def hang() -> None:
        started[0] += 1
        await asyncio.sleep(30)

    task = asyncio.create_task(supervise_step(StepSpec("hang", 0.01, 0.05), hang, stop, liveness))
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.wait_for(task, 3)
    assert liveness.steps["hang"].last_error == "step_timeout" and started[0] >= 1


@pytest.mark.asyncio
async def test_readiness_needs_a_fresh_heartbeat_and_no_stalled_critical_step(
    task_db: Fixture,
) -> None:
    db, *_ = task_db
    record = StepLiveness(StepSpec("reconcile", 10, 300))
    record.registered_at = utcnow() - timedelta(seconds=600)
    assert record.stalled(utcnow())
    record.busy = True
    assert not record.stalled(utcnow())
    record.busy, record.succeeded_at = False, utcnow()
    assert not record.stalled(utcnow())
    record.started_at = utcnow() - timedelta(seconds=600)
    assert record.stalled(utcnow())  # A hung iteration is stalled even after a success.

    async def write(liveness: dict[str, Any], age: float = 0) -> None:
        async with db.sessions() as session, session.begin():
            row = await session.get(GatewayRow, "gw-test")
            if row is None:
                row = GatewayRow(id="gw-test", state="running")
                session.add(row)
            row.heartbeat_at = utcnow() - timedelta(seconds=age)
            row.liveness = liveness

    stalled = {"steps": {"reconcile": {"critical": True, "stalled": True}}}
    await write(stalled)
    health = await gateway_health(db)
    assert health["ready"] is False and health["stalled"] == {"gw-test": ["reconcile"]}
    await write({"steps": {"charts": {"critical": False, "stalled": True}}})
    assert (await gateway_health(db))["ready"] is True
    await write({"steps": {}}, age=120)
    assert (await gateway_health(db))["ready"] is False


@pytest.mark.asyncio
async def test_the_heartbeat_refreshes_the_file_the_container_healthcheck_reads(
    task_db: Fixture, tmp_path: Path
) -> None:
    db, *_ = task_db
    alive = tmp_path / "state" / "gateway-alive"
    gateway = service.Gateway(db, "unused-key", tmp_path, liveness_file=alive)
    await gateway.heartbeat()
    first = alive.stat().st_mtime
    os.utime(alive, (first - 600, first - 600))
    await gateway.heartbeat()
    assert alive.stat().st_mtime > first - 600


def test_the_gateway_service_is_healthy_only_while_its_heartbeat_file_is_fresh() -> None:
    import yaml
    from lonora_worker.health import LIVENESS_FILE

    # A stuck loop, a dead process or a heartbeat that cannot reach the database lets the
    # file age, and the container turns unhealthy.
    compose = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "infra/compose/docker-compose.prod.yml").read_text()
    )
    check = compose["services"]["gateway"]["healthcheck"]
    assert "/app/" + str(LIVENESS_FILE) in " ".join(check["test"])
    assert check["interval"] and check["retries"] and check["start_period"]


def watch_payload(**extra: Any) -> dict[str, Any]:
    return {
        "kind": "price",
        "account_id": "acc",
        "symbol": "XAUUSD",
        "prompt": "Tell me when gold moves",
        "condition": "above",
        "level": "1",
        **extra,
    }


@pytest.mark.asyncio
async def test_watches_are_filtered_and_ordered_in_sql_and_a_poison_watch_is_isolated(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    now = utcnow()

    def watch(state: dict[str, Any], **payload: Any) -> MarketWatchRow:
        return MarketWatchRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            payload=watch_payload(**payload),
            state=state,
        )

    fresh = watch({})
    poison = watch({"next_check": (now - timedelta(seconds=120)).isoformat()})
    overdue = watch({"next_check": (now - timedelta(seconds=60)).isoformat()})
    future = watch({"next_check": (now + timedelta(seconds=600)).isoformat()})
    disabled = watch({}, enabled=False)
    expired = watch({"lifecycle": "expired"})
    async with db.sessions() as session, session.begin():
        session.add_all([fresh, poison, overdue, future, disabled, expired])
    seen: list[str] = []

    async def check(
        _: Database, __: BrokerManager, original: MarketWatchRow, *args: Any, **kwargs: Any
    ) -> int:
        seen.append(original.id)
        if original.id == poison.id:
            raise KeyError("symbol")
        return 0

    monkeypatch.setattr(watchers, "check_watch", check)
    await watchers.check_watches(db, NO_BROKERS)
    # Never-checked first, then most overdue; retired and future rows never take a slot.
    assert seen == [fresh.id, poison.id, overdue.id]
    assert (await failure(db, "watch", poison.id)).failures == 1  # type: ignore[union-attr]
    seen.clear()
    await watchers.check_watches(db, NO_BROKERS)
    assert poison.id not in seen and set(seen) == {fresh.id, overdue.id}
    for _ in range(QUARANTINE_AFTER - 1):
        await expire_backoff(db, "watch")
        await watchers.check_watches(db, NO_BROKERS)
    async with db.sessions() as session:
        row = await session.get(MarketWatchRow, poison.id)
    assert row and row.payload["enabled"] is False and row.state["code"] == "watch_quarantined"
    items = await system_items(db, owner, "maintenance_item_quarantined")
    assert [item.parameters["item_kind"] for item in items] == ["watch"]


@pytest.mark.asyncio
async def test_a_hung_watch_observation_times_out_as_unavailable_health(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        row = MarketWatchRow(
            owner_id=owner, agent_id=agent, thread_id=thread, payload=watch_payload(), state={}
        )
        session.add(row)

    async def hang(*_: Any, **__: Any) -> Any:
        await asyncio.sleep(30)

    monkeypatch.setattr(watchers, "WATCH_OBSERVATION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(watchers, "observe", hang)
    assert await watchers.check_watches(db, NO_BROKERS) == 0
    async with db.sessions() as session:
        current = await session.get(MarketWatchRow, row.id)
    assert current and current.state["health"]["reason_code"] == "watch_observation_timeout"
    assert current.state.get("next_check")
    # A source failure is watch health, not a maintenance failure.
    assert await failure(db, "watch", row.id) is None


@pytest.mark.asyncio
async def test_a_poison_attention_event_never_holds_the_cursor_and_is_quarantined(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        for identifier in ("missing-1", "poison", "missing-3"):
            emit(
                session,
                owner,
                "task.failed",
                agent_id=agent,
                payload={"id": identifier, "attempt": 1, "recovery": "owner"},
            )
    real = attention.candidate

    async def poisoned(db_: Database, brokers: BrokerManager, event: EventRow, **kw: Any) -> Any:
        if event.payload.get("id") == "poison":
            raise KeyError("origin_thread_id")
        return await real(db_, brokers, event, **kw)

    monkeypatch.setattr(attention, "candidate", poisoned)
    await attention.attention_tick(db, NO_BROKERS, owner)
    async with db.sessions() as session:
        events = list(
            await session.scalars(
                select(EventRow).where(EventRow.owner_id == owner, EventRow.kind == "task.failed")
            )
        )
        counter = await session.get(SettingRow, "attention-cursor:" + owner)
        receipts = {
            event.payload["id"]: await session.get(
                EffectReceiptRow, "attention-source:" + owner + ":" + str(event.cursor)
            )
            for event in events
        }
    poison_event = next(event for event in events if event.payload["id"] == "poison")
    # The cursor moved past the poison event; the others were decided.
    assert counter and counter.payload["cursor"] == max(
        int(event.payload["_ln_public_cursor"]) for event in events
    )
    assert receipts["missing-1"] and receipts["missing-3"] and receipts["poison"] is None
    assert await failure(db, "attention_event", str(poison_event.cursor))
    for _ in range(QUARANTINE_AFTER - 1):
        await expire_backoff(db, "attention_event")
        await attention.attention_tick(db, NO_BROKERS, owner)
    async with db.sessions() as session:
        receipt = await session.get(
            EffectReceiptRow, "attention-source:" + owner + ":" + str(poison_event.cursor)
        )
    assert receipt and receipt.result["reason_code"] == "attention_projection_failed"
    assert await failure(db, "attention_event", str(poison_event.cursor)) is None
    items = await system_items(db, owner, "maintenance_item_quarantined")
    assert [item.parameters["item_kind"] for item in items] == ["attention_event"]


async def crash_until_capped(db: Database, owner: str, agent: str, title: str) -> str:
    async with db.sessions() as session, session.begin():
        thread = ThreadRow(owner_id=owner, agent_id=agent, title=title)
        session.add(thread)
        await session.flush()
        run = await create_run(
            session,
            owner,
            RunRequest(thread_id=thread.id, agent_id=agent, prompt="crash me"),
        )
    for attempt in range(MAX_RUN_RECOVERIES + 1):
        async with db.sessions() as session, session.begin():
            claimed = await claim_next(session, "gw-crash", 60)
            assert claimed and claimed.id == run.id and claimed.recovery_count == attempt
            # The worker dies holding the lease.
            claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
    async with db.sessions() as session, session.begin():
        # Past the cap nobody re-leases it: the watchdog decides.
        assert await claim_next(session, "gw-crash", 60) is None
    return run.id


@pytest.mark.asyncio
async def test_a_run_recovered_too_often_is_quarantined_unless_a_trade_is_uncertain(
    task_db: Fixture,
) -> None:
    db, owner, agent, _ = task_db
    plain = await crash_until_capped(db, owner, agent, "plain")
    financial = await crash_until_capped(db, owner, agent, "financial")
    async with db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id="op-held",
                owner_id=owner,
                account_id="acc",
                request_hash="h",
                request={"symbol": "XAUUSD"},
                status="submitted",
                submitted_at=utcnow(),
                result={"details": {"execution": {"run_id": financial, "agent_id": agent}}},
            )
        )
    watchdog = Watchdog(db, Liveness(), set())
    assert await watchdog.recovered_runs() == 1
    async with db.sessions() as session:
        failed = await session.get(RunRow, plain)
        held = await session.get(RunRow, financial)
    assert failed and failed.status == "failed" and failed.error_code == "run_recovery_limit"
    # Never failed silently over an uncertain trade: it waits for reconciliation.
    assert held and held.status in {"leased", "running"}
    items = await system_items(db, owner, "run_quarantined")
    assert [item.parameters["run_id"] for item in items] == [plain]
    # The item opens the agent and conversation where the work stopped.
    assert (items[0].agent_id, items[0].thread_id) == (agent, failed.thread_id)
    async with db.sessions() as session, session.begin():
        journal = await session.get(TradingJournalRow, "op-held")
        assert journal
        journal.status = "confirmed"
    assert await watchdog.recovered_runs() == 1
    async with db.sessions() as session:
        settled = await session.get(RunRow, financial)
    assert settled and settled.status == "failed"


@pytest.mark.asyncio
async def test_the_watchdog_reports_aging_operations_overdue_wakes_and_stalls_once(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        desk = ThreadRow(owner_id=owner, agent_id=agent, title="Gold desk")
        session.add(desk)
        await session.flush()
        placed = RunRow(thread_id=desk.id, agent_id=agent, status="completed")
        session.add(placed)
        await session.flush()
        session.add(
            TradingJournalRow(
                operation_id="op-aging",
                owner_id=owner,
                account_id="acc",
                request_hash="h",
                request={"symbol": "XAUUSD"},
                status="ambiguous",
                submitted_at=utcnow() - timedelta(hours=1),
                result={"details": {"execution": {"agent_id": agent, "run_id": placed.id}}},
            )
        )
        session.add(
            RoutineRow(
                owner_id=owner,
                agent_id=agent,
                thread_id=thread,
                prompt="late",
                interval_seconds=60,
                next_run_at=utcnow() - timedelta(hours=1),
            )
        )
    liveness = Liveness()
    stalled = liveness.register(StepSpec("reconcile", 10, 300))
    stalled.registered_at = utcnow() - timedelta(hours=1)
    watchdog = Watchdog(db, liveness, set())
    quiet = {"steps": 0, "runs": 0, "overdue": 0, "delayed": 0, "operations": 0, "ended": 0}
    assert await watchdog.tick() == {**quiet, "steps": 1, "overdue": 1, "operations": 1}
    # One item per operation and per episode: a second pass raises nothing new.
    assert await watchdog.tick() == quiet
    operation = await system_items(db, owner, "operation_unresolved")
    assert len(operation) == 1 and operation[0].parameters["symbol"] == "XAUUSD"
    assert operation[0].importance == "action_required"
    # It opens the conversation of the Run that placed the trade.
    assert (operation[0].agent_id, operation[0].thread_id) == (agent, desk.id)
    degraded = await system_items(db, owner, "gateway_degraded")
    assert sorted(item.parameters["reason_code"] for item in degraded) == [
        "step_stalled",
        "wakes_overdue",
    ]
    # Once the condition clears, the unread item is withdrawn instead of going stale.
    stalled.succeeded_at = utcnow()
    async with db.sessions() as session, session.begin():
        journal = await session.get(TradingJournalRow, "op-aging")
        assert journal
        journal.status = "confirmed"
    await watchdog.tick()
    assert "step:reconcile" not in watchdog.episodes
    statuses = {
        item.parameters["reason_code"]: item.status
        for item in await system_items(db, owner, "gateway_degraded")
    }
    assert statuses == {"step_stalled": "suppressed", "wakes_overdue": "ready"}
    assert [item.status for item in await system_items(db, owner, "operation_unresolved")] == [
        "suppressed"
    ]


@pytest.mark.asyncio
async def test_an_owner_message_left_queued_opens_one_episode_until_it_is_claimed(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    waited = utcnow() - timedelta(seconds=61)
    async with db.sessions() as session, session.begin():
        message = await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="Gold now?")
        )
        message.created_at = message.updated_at = waited
        # Background work and a run waiting out its retry backoff are not delayed.
        work = ThreadRow(owner_id=owner, agent_id=agent, title="Routine", purpose="work")
        session.add(work)
        await session.flush()
        session.add(
            RunRow(
                thread_id=work.id,
                agent_id=agent,
                trigger="routine",
                created_at=waited,
                updated_at=waited,
            )
        )
        later = (utcnow() + timedelta(minutes=5)).isoformat()
        retrying = ThreadRow(owner_id=owner, agent_id=agent, title="Retrying")
        session.add(retrying)
        await session.flush()
        session.add(
            RunRow(
                thread_id=retrying.id,
                agent_id=agent,
                execution_state={"environment": {"retry": {"not_before": later}}},
                created_at=waited,
                updated_at=waited,
            )
        )
        # Waiting behind its own conversation's running turn is not the workers' delay.
        busy = ThreadRow(owner_id=owner, agent_id=agent, title="Busy")
        session.add(busy)
        await session.flush()
        session.add(
            RunRow(
                thread_id=busy.id,
                agent_id=agent,
                status="running",
                lease_expires_at=utcnow() + timedelta(minutes=2),
            )
        )
        session.add(RunRow(thread_id=busy.id, agent_id=agent, created_at=waited, updated_at=waited))
    watchdog = Watchdog(db, Liveness(), set())
    assert await watchdog.delayed_runs() == 1
    assert await watchdog.delayed_runs() == 0  # One item per episode.
    [item] = await system_items(db, owner, "gateway_degraded")
    assert item.parameters["reason_code"] == "runs_delayed"
    assert item.parameters["count"] == 1 and item.parameters["oldest_seconds"] >= 61
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, "worker-test", 120)
        assert claimed is not None and claimed.id == message.id
    assert await watchdog.delayed_runs() == 0
    assert "delayed" not in watchdog.episodes
    assert [row.status for row in await system_items(db, owner, "gateway_degraded")] == [
        "suppressed"
    ]


@pytest.mark.asyncio
async def test_a_fired_one_shot_switched_back_on_is_not_an_overdue_wake(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        past = utcnow() - timedelta(hours=1)
        session.add(
            RoutineRow(
                owner_id=owner,
                agent_id=agent,
                thread_id=thread,
                prompt="once",
                run_at=past,
                next_run_at=past,
                last_run_at=past,
                # It fired, then something switched it back on without a new time.
                enabled=True,
            )
        )
    watchdog = Watchdog(db, Liveness(), set())
    assert await watchdog.overdue_wakes() == 0
    assert "overdue" not in watchdog.episodes
    assert await system_items(db, owner, "gateway_degraded") == []


@pytest.mark.asyncio
async def test_drain_releases_leases_with_the_fence_kept_so_resume_is_immediate(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        run = await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="long work")
        )
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, "gw-old", 120)
        assert claimed and claimed.id == run.id and claimed.lease_fence == 1
        claimed.status = "running"
    async with db.sessions() as session, session.begin():
        assert await release_leases(session, "gw-other") == []
        assert await release_leases(session, "gw-old") == [run.id]
    async with db.sessions() as session:
        released = await session.get(RunRow, run.id)
        assert released and released.status == "queued" and released.lease_fence == 1
        assert released.lease_expires_at is None
        with pytest.raises(LonoraError) as stale:
            await require_lease(session, Lease(run_id=run.id, owner="gw-old", fence=1))
        assert stale.value.code == "stale_lease"
    async with db.sessions() as session, session.begin():
        resumed = await claim_next(session, "gw-new", 120)
        assert resumed and resumed.id == run.id and resumed.lease_fence == 2
        # A drain is a clean hand-over, not a crash recovery.
        assert resumed.recovery_count == 0


@pytest.mark.asyncio
async def test_the_gateway_releases_its_leases_when_it_drains(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db, owner, agent, thread = task_db
    monkeypatch.setattr(service, "STEPS", ())
    gateway = service.Gateway(db, "unused-key", tmp_path, maximum_subagents=0)

    async def idle(lane: str | None = None, name: str = "worker") -> None:
        await gateway.stop.wait()

    monkeypatch.setattr(gateway, "worker_loop", idle)
    async with db.sessions() as session, session.begin():
        run = await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="drain me")
        )
    async with db.sessions() as session, session.begin():
        assert await claim_next(session, gateway.identity, 120)
    serving = asyncio.create_task(gateway.serve())
    await asyncio.sleep(0.05)
    gateway.request_stop()
    await asyncio.wait_for(serving, 5)
    async with db.sessions() as session:
        row = await session.get(RunRow, run.id)
        heartbeat = await session.get(GatewayRow, gateway.identity)
    assert row and row.status == "queued" and row.lease_fence == 1
    assert heartbeat and heartbeat.state == "stopped"


@pytest.mark.asyncio
async def test_the_gateway_tells_its_runs_to_hand_back_before_it_drains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service, "STEPS", ())
    gateway = service.Gateway(
        cast(Database, SimpleNamespace()), "unused-key", tmp_path, maximum_subagents=0
    )
    given: list[RunDrain | None] = []

    async def dispatch(*_: Any, drain: RunDrain | None = None, **__: Any) -> bool:
        given.append(drain)
        return False

    seen: list[bool] = []

    async def draining(tasks: list[asyncio.Task[None]], *_: Any, **__: Any) -> None:
        seen.append(gateway.run_drain.requested)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def nothing(*_: Any, **__: Any) -> Any:
        return None

    monkeypatch.setattr(service, "dispatch_one", dispatch)
    monkeypatch.setattr(service, "drain", draining)
    monkeypatch.setattr(service, "write_heartbeat", nothing)
    monkeypatch.setattr(service, "release_leases", nothing)
    serving = asyncio.create_task(gateway.serve())
    await asyncio.sleep(0.05)
    assert not gateway.run_drain.requested
    gateway.request_stop()
    await asyncio.wait_for(serving, 5)
    # Every worker hands its Runs the Gateway's one signal, set before the drain starts.
    assert given and all(drain is gateway.run_drain for drain in given)
    assert seen == [True]


@pytest.mark.asyncio
async def test_the_backstop_cancels_a_busy_worker_but_never_one_inside_an_effect() -> None:
    effects: set[asyncio.Task[Any]] = set()
    finished: list[str] = []

    async def streaming() -> None:
        # A model stream that does not end: the backstop is what stops it.
        await asyncio.sleep(60)

    async def sending() -> None:
        effects.add(cast(asyncio.Task[Any], asyncio.current_task()))
        try:
            await asyncio.sleep(0.6)
        finally:
            effects.discard(cast(asyncio.Task[Any], asyncio.current_task()))
        finished.append("sent")

    async def stuck() -> None:
        effects.add(cast(asyncio.Task[Any], asyncio.current_task()))
        await asyncio.sleep(60)

    clock = asyncio.get_running_loop().time
    busy, effect = asyncio.create_task(streaming()), asyncio.create_task(sending())
    started = clock()
    await drain([busy, effect], 0.1, 5, effects)
    # The send ran to its own end long after the backstop; the stream was cut at it.
    assert busy.cancelled() and not effect.cancelled() and finished == ["sent"]
    assert 0.5 < clock() - started < 2
    # Only the one shutdown deadline cuts an effect that never ends.
    hung = asyncio.create_task(stuck())
    started = clock()
    await drain([hung], 0.1, 0.5, effects)
    assert hung.cancelled() and 0.4 < clock() - started < 1.5


@pytest.mark.asyncio
async def test_shutdown_releases_leases_inside_one_deadline_below_the_stop_grace(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db, owner, agent, thread = task_db
    monkeypatch.setattr(service, "STEPS", ())
    monkeypatch.setattr(service, "BACKSTOP_SECONDS", 0.2)
    monkeypatch.setattr(service, "SHUTDOWN_SECONDS", 1.0)
    gateway = service.Gateway(db, "unused-key", tmp_path, maximum_subagents=0)

    async def busy(lane: str | None = None, name: str = "worker") -> None:
        # A worker inside a model call that does not end before the backstop.
        await asyncio.sleep(60)

    answered: list[str] = []

    async def order() -> None:
        # An owner's relayed order that needs longer than the backstop.
        await asyncio.sleep(0.5)
        answered.append("order")

    monkeypatch.setattr(gateway, "worker_loop", busy)
    async with db.sessions() as session, session.begin():
        run = await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="drain me")
        )
    async with db.sessions() as session, session.begin():
        assert await claim_next(session, gateway.identity, 120)
    serving = asyncio.create_task(gateway.serve())
    await asyncio.sleep(0.05)
    gateway.relay.tasks.add(asyncio.create_task(order()))
    # A request that never ends gives up at the shutdown deadline, not after it.
    gateway.relay.tasks.add(asyncio.create_task(asyncio.sleep(60)))
    clock = asyncio.get_running_loop().time
    started = clock()
    gateway.request_stop()
    await asyncio.wait_for(serving, 5)
    # The run drain and the relay drain ran at the same time, inside the one deadline.
    assert clock() - started < 1.6 and answered == ["order"]
    async with db.sessions() as session:
        row = await session.get(RunRow, run.id)
    assert row and row.status == "queued" and row.lease_fence == 1
    for task in gateway.relay.tasks:
        task.cancel()


def test_the_stop_grace_leaves_room_after_the_shutdown_deadline() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "infra/compose/docker-compose.prod.yml").read_text())
    grace = compose["services"]["gateway"]["stop_grace_period"]
    unit = (root / "infra/systemd/lonora-gateway.service").read_text()
    timeout = next(
        line.split("=", 1)[1] for line in unit.splitlines() if line.startswith("TimeoutStopSec=")
    )
    assert service.BACKSTOP_SECONDS < service.SHUTDOWN_SECONDS
    # Releasing leases and closing connections still fit before Docker or systemd kills.
    for seconds in (int(grace.removesuffix("s")), int(timeout)):
        assert seconds >= service.SHUTDOWN_SECONDS + 10


def test_every_gateway_iteration_is_a_scheduled_step(tmp_path: Path) -> None:
    # start() schedules STEPS only: an iteration without a StepSpec never runs in production.
    gateway = service.Gateway(
        cast(Database, SimpleNamespace()), "unused-key", tmp_path, maximum_subagents=0
    )
    assert {spec.name for spec in service.STEPS} == set(gateway.iterations())


@pytest.mark.asyncio
async def test_closed_trades_wake_their_owners_from_a_scheduled_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 5.5.2: close_wakes is scheduled, and each pass wakes every owner's closed trades.
    import lonora_trading.close_wake as close_wake

    db = cast(Database, SimpleNamespace())
    gateway = service.Gateway(db, "unused-key", tmp_path, maximum_subagents=0)
    woken: list[tuple[Database, str]] = []

    async def wake(database: Database, owner_id: str) -> int:
        woken.append((database, owner_id))
        return 0

    monkeypatch.setattr(close_wake, "wake_for_closes", wake)
    gateway.services = {"owner-1": cast(OwnerServices, SimpleNamespace(owner_id="owner-1"))}
    assert "close_wakes" in {spec.name for spec in service.STEPS}
    await gateway.iterations()["close_wakes"]()
    assert woken == [(db, "owner-1")]


async def leased(db: Database, owner: str, agent: str, thread: str) -> ToolContext:
    async with db.sessions() as session, session.begin():
        run = await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="renew")
        )
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, "gw-renew", 60)
        assert claimed and claimed.id == run.id
        lease = Lease(run_id=run.id, owner="gw-renew", fence=claimed.lease_fence)
    return cast(ToolContext, SimpleNamespace(db=db, lease=lease))


@pytest.mark.asyncio
async def test_lease_renewal_retries_a_transient_database_error(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    context = await leased(db, owner, agent, thread)
    attempts: list[int] = []
    real = executor.renew_lease

    async def flaky(session: Any, lease: Lease, seconds: int) -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError("UPDATE ln_runs", {}, ConnectionResetError("reset"))
        await real(session, lease, seconds)

    monkeypatch.setattr(executor, "renew_lease", flaky)
    lost: list[bool] = []
    task = asyncio.create_task(executor.keep_lease(context, 3, lambda: lost.append(True)))
    await asyncio.sleep(1.6)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert not lost and len(attempts) >= 2


@pytest.mark.asyncio
async def test_lease_renewal_gives_up_before_expiry_or_at_once_when_fenced(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    context = await leased(db, owner, agent, thread)

    async def down(*_: Any) -> None:
        raise OperationalError("UPDATE ln_runs", {}, ConnectionRefusedError("down"))

    monkeypatch.setattr(executor, "renew_lease", down)
    lost: list[bool] = []
    task = asyncio.create_task(executor.keep_lease(context, 3, lambda: lost.append(True)))
    await asyncio.wait_for(task, 4)
    assert lost == [True]

    async def fenced(*_: Any) -> None:
        raise LonoraError("stale_lease", 409)

    monkeypatch.setattr(executor, "renew_lease", fenced)
    lost.clear()
    started = asyncio.get_running_loop().time()
    await asyncio.wait_for(executor.keep_lease(context, 3, lambda: lost.append(True)), 3)
    assert lost == [True] and asyncio.get_running_loop().time() - started < 1.5


async def cancelled_by_owner(context: ToolContext) -> tuple[RunRow, int]:
    """The owner cancels the Run; returns what the cancel wrote and the last event."""
    async with context.db.sessions() as session, session.begin():
        await cancel_run(session, context.owner_id, context.lease.run_id)
    async with context.db.sessions() as session:
        last = await session.scalar(select(func.max(EventRow.cursor)))
    return await saved_run(context), int(last or 0)


async def nothing_written_after(context: ToolContext, cancelled: RunRow, last: int) -> None:
    """No write of the old lease landed after the cancel: the fence refused them all."""
    run = await saved_run(context)
    assert run.status == "cancelled" and run.updated_at == cancelled.updated_at
    assert run.execution_state == cancelled.execution_state
    async with context.db.sessions() as session:
        later = list(
            await session.scalars(
                select(EventRow.kind).where(EventRow.run_id == run.id, EventRow.cursor > last)
            )
        )
    assert later == []


@pytest.mark.asyncio
async def test_a_cancel_during_a_long_model_call_stops_the_run_within_three_seconds(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    thinking = asyncio.Event()

    async def reasoning(*_: Any, **__: Any) -> tuple[ModelReply, ModelSelection]:
        # A reasoning model before its first token: no fenced write would notice a cancel.
        thinking.set()
        await asyncio.sleep(30)
        return ModelReply(text="Too late."), ModelSelection(provider="openai", model="slow")

    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", reasoning)
    context = await conversation_run(task_db)
    worker = asyncio.create_task(executor.execute_run(context, ToolRegistry([]), 120, 8))
    await asyncio.wait_for(thinking.wait(), 5)
    cancelled, last = await cancelled_by_owner(context)
    clock = asyncio.get_running_loop().time
    started = clock()
    await asyncio.wait_for(worker, 5)
    assert clock() - started < 3 and not worker.cancelled()
    await nothing_written_after(context, cancelled, last)


@pytest.mark.asyncio
async def test_a_cancel_never_cuts_a_change_past_before_effect(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, writes = asyncio.Event(), list[int]()

    async def write(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        started.set()
        # Longer than the watcher's period: a cut here would leave the change uncertain.
        await asyncio.sleep(2.5)
        writes.append(args["n"])
        return {"version": args["n"]}

    registry = ToolRegistry([Tool("fixture_write", "Write", Arguments, write, False)])
    block = calls(("w1", "fixture_write", 1))
    context = replace(await conversation_run(task_db, seeded(block)), drain=RunDrain())
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Saved.")))
    worker = asyncio.create_task(executor.execute_run(context, registry, 120, 8))
    await asyncio.wait_for(started.wait(), 5)
    cancelled, last = await cancelled_by_owner(context)
    await asyncio.wait_for(worker, 6)
    # The change ran to its end; its result, written under the old fence, was refused.
    assert writes == [1] and not worker.cancelled()
    await nothing_written_after(context, cancelled, last)


@pytest.mark.asyncio
async def test_a_transient_error_at_the_final_commit_still_completes_the_run(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db)
    monkeypatch.setattr(
        "lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Gold is flat."))
    )
    real = executor.complete_run
    attempts: list[int] = []

    async def flaky(session: Any, lease: Lease, answer: str, metadata: dict[str, Any]) -> bool:
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError("UPDATE ln_runs", {}, ConnectionResetError("reset"))
        return await real(session, lease, answer, metadata)

    monkeypatch.setattr(executor, "complete_run", flaky)
    await executor.execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.status == "completed" and run.result == "Gold is flat.", run.error_code
    assert len(attempts) == 2
    async with context.db.sessions() as session:
        replies = list(
            await session.scalars(
                select(MessageRow).where(
                    MessageRow.thread_id == context.thread_id, MessageRow.role == "assistant"
                )
            )
        )
    # The failed attempt was rolled back: the answer is in the conversation once.
    assert [reply.content for reply in replies] == ["Gold is flat."]


async def handed_back(context: ToolContext) -> RunRow:
    """The Run a draining Gateway released at a step boundary: queued, fence and
    checkpoint kept, no intent marker left behind."""
    run = await saved_run(context)
    assert run.status == "queued" and run.lease_expires_at is None
    assert run.lease_fence == context.lease.fence and run.error_code is None
    environment = run.execution_state["environment"]
    assert environment["retry"]["reason_code"] == "gateway_drained"
    assert "inflight_calls" not in environment and "inflight" not in environment
    async with context.db.sessions() as session:
        released = await session.scalar(
            select(EventRow)
            .where(EventRow.run_id == run.id, EventRow.kind == "run.retry_scheduled")
            .order_by(EventRow.cursor.desc())
            .limit(1)
        )
    assert released and released.payload["reason_code"] == "gateway_drained"
    return run


async def resumed(fixture: Fixture, run_id: str) -> ToolContext:
    """The next claim of a released Run: a new fence, and no recovery counted."""
    db, *_ = fixture
    async with db.sessions() as session, session.begin():
        claimed = await claim_next(session, "gw-next", 120)
        assert claimed and claimed.id == run_id and claimed.recovery_count == 0
        claimed.status = "running"
        lease = Lease(run_id=run_id, owner="gw-next", fence=claimed.lease_fence)
    return context_for(fixture, lease, claimed.thread_id)


@pytest.mark.asyncio
async def test_a_draining_gateway_hands_a_run_back_after_its_slow_read(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    started, reads = asyncio.Event(), list[int]()

    async def slow_read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(0.3)
        reads.append(args["n"])
        return {"price": 2300}

    registry = ToolRegistry([Tool("fixture_read", "Read", Arguments, slow_read, True)])
    stopping = RunDrain()
    context = replace(await conversation_run(task_db), drain=stopping)
    model = Script(
        ModelReply(tool_calls=calls(("r1", "fixture_read", 1))), ModelReply(text="Gold at 2300.")
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    running = asyncio.create_task(executor.execute_run(context, registry, 120, 8))
    await asyncio.wait_for(started.wait(), 5)
    stopping.requested = True
    await asyncio.wait_for(running, 5)
    # The read ended within its own deadline; no model turn started after the signal.
    run = await handed_back(context)
    assert reads == [1] and len(model.requests) == 1
    assert results(run) == {"r1": {"ok": True, "price": 2300}}
    async with db.sessions() as session:
        live = await agent_live_state(session, owner, agent)
    # Handed back is not a retry after a failure: the status line says nothing of one.
    assert live.runtime_waits == [] and live.phase != "recovering"
    # The next claim continues from the same checkpoint: the read is not repeated.
    await executor.execute_run(await resumed(task_db, run.id), registry, 120, 8)
    done = await saved_run(context)
    assert done.status == "completed" and done.result == "Gold at 2300." and reads == [1]
    request, _ = model.requests[1]
    assert [item.tool_call_id for item in request if item.role == "tool"] == ["r1"]


@pytest.mark.asyncio
async def test_a_draining_gateway_never_starts_a_call_or_a_model_turn(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, writes = asyncio.Event(), list[int]()

    async def write(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(0.3)
        writes.append(args["n"])
        return {"version": args["n"]}

    registry = ToolRegistry([Tool("fixture_write", "Write", Arguments, write, False)])
    stopping = RunDrain()
    block = calls(("w1", "fixture_write", 1), ("w2", "fixture_write", 2))
    context = replace(await conversation_run(task_db, seeded(block)), drain=stopping)
    model = Script(ModelReply(text="Both saved."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    running = asyncio.create_task(executor.execute_run(context, registry, 120, 8))
    await asyncio.wait_for(started.wait(), 5)
    stopping.requested = True
    await asyncio.wait_for(running, 5)
    # The change already past before_effect ran to its end; the next one never started.
    run = await handed_back(context)
    assert writes == [1] and model.requests == []
    assert results(run) == {"w1": {"ok": True, "version": 1}}
    assert [call["id"] for call in run.execution_state["pending"]] == ["w2"]
    # A Run that starts while the Gateway drains hands back before anything runs.
    other = replace(await resumed(task_db, run.id), drain=stopping)
    await executor.execute_run(other, registry, 120, 8)
    await handed_back(other)
    assert writes == [1] and model.requests == []
    # The next Gateway runs the second change once and never repeats the first.
    stopping.requested = False
    await executor.execute_run(await resumed(task_db, run.id), registry, 120, 8)
    done = await saved_run(context)
    assert done.status == "completed" and writes == [1, 2]
    assert set(results(done)) == {"w1", "w2"} and len(model.requests) == 1


@pytest.mark.asyncio
async def test_the_backstop_never_cuts_a_change_past_before_effect(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, writes = asyncio.Event(), list[int]()

    async def write(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        started.set()
        # Longer than the backstop: a cut here would leave the change uncertain.
        await asyncio.sleep(0.6)
        writes.append(args["n"])
        return {"version": args["n"]}

    registry = ToolRegistry([Tool("fixture_write", "Write", Arguments, write, False)])
    stopping = RunDrain()
    block = calls(("w1", "fixture_write", 1))
    context = replace(await conversation_run(task_db, seeded(block)), drain=stopping)
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", Script(ModelReply(text="Saved.")))
    worker = asyncio.create_task(executor.execute_run(context, registry, 120, 8))
    await asyncio.wait_for(started.wait(), 5)
    assert stopping.effects == {worker}
    stopping.requested = True
    await drain([worker], 0.1, 5, stopping.effects)
    # The change ran to its end, its result was checkpointed, then the Run handed back.
    assert not worker.cancelled() and writes == [1] and stopping.effects == set()
    run = await handed_back(context)
    assert results(run) == {"w1": {"ok": True, "version": 1}}


# A retired Super Bot request keeps the id of the goal it named, as a value.
RETIRED_GOAL = "retired-goal"


async def financial_fixture(db: Database, owner: str) -> dict[str, str]:
    async with db.sessions() as session, session.begin():
        agent = AgentRow(owner_id=owner, name="Gold desk")
        session.add(agent)
        await session.flush()
        thread = ThreadRow(owner_id=owner, agent_id=agent.id, title="Gold")
        account = BrokerSessionRow(owner_id=owner, payload={"provider": "simulation"})
        session.add_all([thread, account])
        await session.flush()
        run = RunRow(thread_id=thread.id, agent_id=agent.id, status="completed")
        session.add(run)
        await session.flush()
        now = utcnow()
        session.add_all(
            [
                AccountAuthorityRow(
                    owner_id=owner,
                    agent_id=agent.id,
                    thread_id=thread.id,
                    account_id=account.id,
                    status="active",
                    envelope={"account_id": account.id},
                    envelope_hash="hash",
                    activation_expires_at=now,
                ),
                TradeApprovalRow(
                    id="ap-" + run.id[:8],
                    owner_id=owner,
                    run_id=run.id,
                    thread_id=thread.id,
                    agent_id=agent.id,
                    call_id="call",
                    requests=[{"account_id": account.id, "symbol": "XAUUSD"}],
                    status="completed",
                ),
                SuperBotRequestRow(
                    owner_id=owner,
                    agent_id=agent.id,
                    thread_id=thread.id,
                    goal_id=RETIRED_GOAL,
                    mode="advisory",
                    status="cancelled",
                    envelope={"symbol": "XAUUSD"},
                    envelope_hash="hash",
                    expires_at=now,
                ),
            ]
        )
    return {
        "agent": agent.id,
        "thread": thread.id,
        "account": account.id,
        "run": run.id,
    }


@pytest.mark.asyncio
@pytest.mark.skipif(not POSTGRES, reason="Cascades need PostgreSQL foreign keys.")
async def test_deleting_a_conversation_agent_or_account_keeps_financial_records(
    task_db: Fixture,
) -> None:
    db, owner, _, _ = task_db
    ids = await financial_fixture(db, owner)
    for row_type, identifier in (
        (ThreadRow, ids["thread"]),
        (AgentRow, ids["agent"]),
        (BrokerSessionRow, ids["account"]),
    ):
        async with db.sessions() as session, session.begin():
            row = await session.get(row_type, identifier)
            assert row is not None
            await session.delete(row)
    async with db.sessions() as session:
        authority = await session.scalar(
            select(AccountAuthorityRow).where(AccountAuthorityRow.owner_id == owner)
        )
        approval = await session.get(TradeApprovalRow, "ap-" + ids["run"][:8])
        request = await session.scalar(
            select(SuperBotRequestRow).where(SuperBotRequestRow.owner_id == owner)
        )
    # Contextual links are cleared; identity links keep the id they recorded.
    assert authority and authority.thread_id is None
    assert (authority.agent_id, authority.account_id) == (ids["agent"], ids["account"])
    assert approval and approval.run_id is None and approval.thread_id is None
    assert approval.agent_id == ids["agent"]
    assert request and request.thread_id is None and request.goal_id == RETIRED_GOAL


@pytest.mark.asyncio
async def test_a_delete_is_refused_while_its_trade_is_uncertain_then_narrows_authority(
    task_db: Fixture,
) -> None:
    db, owner, _, _ = task_db
    ids = await financial_fixture(db, owner)
    async with db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id="op-uncertain",
                owner_id=owner,
                account_id=ids["account"],
                request_hash="h",
                request={"symbol": "XAUUSD"},
                status="ambiguous",
                result={"details": {"execution": {"agent_id": ids["agent"]}}},
            )
        )
        session.add(
            TradeApprovalRow(
                id="approval-pending",
                owner_id=owner,
                run_id=ids["run"],
                thread_id=ids["thread"],
                agent_id=ids["agent"],
                call_id="later",
                requests=[{"account_id": ids["account"], "symbol": "XAUUSD"}],
                status="pending",
            )
        )
        session.add(
            TradeApprovalRow(
                id="approval-unsent",
                owner_id=owner,
                run_id=ids["run"],
                thread_id=ids["thread"],
                agent_id=ids["agent"],
                call_id="unsent",
                requests=[{"account_id": ids["account"], "symbol": "XAUUSD"}],
                status="approved",
            )
        )
    for scope in (
        {"agent_id": ids["agent"]},
        {"account_id": ids["account"]},
    ):
        async with db.sessions() as session, session.begin():
            with pytest.raises(LonoraError) as refused:
                await prepare_delete(session, owner, **scope)
            assert refused.value.code == "delete_blocked_unresolved_operation"
            assert refused.value.status == 409
    async with db.sessions() as session, session.begin():
        journal = await session.get(TradingJournalRow, "op-uncertain")
        assert journal
        journal.status = "confirmed"
    async with db.sessions() as session, session.begin():
        await prepare_delete(session, owner, agent_id=ids["agent"])
    async with db.sessions() as session:
        pending = await session.get(TradeApprovalRow, "approval-pending")
        unsent = await session.get(TradeApprovalRow, "approval-unsent")
        completed = await session.get(TradeApprovalRow, "ap-" + ids["run"][:8])
        authority = await session.scalar(
            select(AccountAuthorityRow).where(AccountAuthorityRow.owner_id == owner)
        )
    # Narrowing never needs the owner: the pending request is cancelled, the grant revoked.
    assert pending and pending.status == "cancelled"
    # Approved but never sent has no money effect yet: it is cancelled, not a blocker.
    assert unsent and unsent.status == "cancelled"
    assert completed and completed.status == "completed"
    assert authority and authority.status == "revoked"


@pytest.mark.asyncio
async def test_an_item_guard_never_quarantines_financial_kinds(task_db: Fixture) -> None:
    db, owner, *_ = task_db
    guard = ItemGuard(db, "opportunity", quarantine_after=None)

    async def broken() -> None:
        raise ConnectionError("broker")

    for _ in range(QUARANTINE_AFTER + 2):
        await expire_backoff(db, "opportunity")
        assert await guard.run("op-1", owner, broken) is None
    recorded = await failure(db, "opportunity", "op-1")
    assert (
        recorded and recorded.quarantined_at is None and recorded.failures == QUARANTINE_AFTER + 2
    )
    assert not await system_items(db, owner, "maintenance_item_quarantined")


@pytest.mark.asyncio
async def test_two_gateways_recording_one_items_first_failure_both_count(
    task_db: Fixture,
) -> None:
    # A rolling restart overlaps two gateways on the same poison item: neither may
    # escape ``run`` with a duplicate-key error, and both failures count once each.
    db, owner, *_ = task_db

    async def broken() -> None:
        raise ValueError("poison")

    # Two pooled connections, so neither first failure waits for a new one to open.
    async with db.engine.connect(), db.engine.connect():
        pass
    results = await asyncio.gather(
        *(ItemGuard(db, "routine").run("race-item", owner, broken) for _ in range(2)),
        return_exceptions=True,
    )
    assert results == [None, None], results
    recorded = await failure(db, "routine", "race-item")
    assert recorded and recorded.code == "unexpected_value_error"
    # The row lock counts both on PostgreSQL; the shared in-memory sqlite connection
    # has no row locks, so there only the missing duplicate-key error is the contract.
    if POSTGRES:
        assert recorded.failures == 2, recorded.failures


@pytest.mark.asyncio
async def test_deleting_a_conversation_settles_its_grant_and_keeps_retired_history(
    task_db: Fixture,
) -> None:
    db, owner, _, _ = task_db
    ids = await financial_fixture(db, owner)
    async with db.sessions() as session, session.begin():
        session.add(
            SuperBotRequestRow(
                id="sb-live",
                owner_id=owner,
                agent_id=ids["agent"],
                thread_id=ids["thread"],
                goal_id=RETIRED_GOAL,
                mode="autonomous",
                status="retired",
                envelope={"symbol": "XAUUSD"},
                envelope_hash="hash",
                expires_at=utcnow(),
            )
        )
    async with db.sessions() as session, session.begin():
        await prepare_delete(session, owner, thread_id=ids["thread"])
        thread = await session.get(ThreadRow, ids["thread"])
        assert thread
        await session.delete(thread)
    async with db.sessions() as session:
        grant = await session.scalar(
            select(AccountAuthorityRow).where(AccountAuthorityRow.owner_id == owner)
        )
        assert grant and grant.status == "revoked"
        # Records, the permission frame and the trade path tell the same story.
        with pytest.raises(LonoraError) as unusable:
            await require_authority(session, owner, ids["agent"], grant.id)
        assert unusable.value.code == "account_authority_unavailable"
        frame = await permission_state(session, owner, ids["agent"])
        assert frame["status"] == "autonomous_stopped"
        assert frame["effective_level"] != "autonomous" and not frame["active_authorities"]
        request = await session.get(SuperBotRequestRow, "sb-live", populate_existing=True)
    # A retired Super Bot request is audit history only: nothing settles or reads it.
    assert request and request.status == "retired"


@pytest.mark.asyncio
async def test_a_hanging_attention_event_times_out_into_the_ledger_and_never_holds_the_cursor(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await ensure_personal_agent(session, owner)
    # Lonora's onboarding events are decided first: these three are then the only new ones.
    await attention.attention_tick(db, NO_BROKERS, owner)
    async with db.sessions() as session, session.begin():
        for identifier in ("before", "hang", "after"):
            emit(
                session,
                owner,
                "task.failed",
                agent_id=agent,
                payload={"id": identifier, "attempt": 1, "recovery": "owner"},
            )
    real = attention.candidate

    async def hanging(db_: Database, brokers: BrokerManager, event: EventRow, **kw: Any) -> Any:
        if event.payload.get("id") == "hang":
            await asyncio.Event().wait()
        return await real(db_, brokers, event, **kw)

    monkeypatch.setattr(attention, "candidate", hanging)

    async def state() -> tuple[int, dict[str, int], dict[str, bool]]:
        async with db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.owner_id == owner, EventRow.kind == "task.failed"
                    )
                )
            )
            counter = await session.get(
                SettingRow, "attention-cursor:" + owner, populate_existing=True
            )
            decided = {
                event.payload["id"]: await session.get(
                    EffectReceiptRow, "attention-source:" + owner + ":" + str(event.cursor)
                )
                is not None
                for event in events
            }
        positions = {
            event.payload["id"]: int(event.payload["_ln_public_cursor"]) for event in events
        }
        return int(counter.payload["cursor"]) if counter else 0, positions, decided

    # The step's iteration timeout cancels the batch: what was already decided is kept.
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(3.0):
            await attention.attention_tick(db, NO_BROKERS, owner)
    cursor, positions, decided = await state()
    assert cursor == positions["before"] and decided["before"] and not decided["after"]
    # Its own item limit turns the hang into a recorded failure; later events are decided.
    monkeypatch.setattr(item_failures, "ITEM_TIMEOUT_SECONDS", 0.2)
    await asyncio.wait_for(attention.attention_tick(db, NO_BROKERS, owner), 10)
    cursor, positions, decided = await state()
    # Every attention event of the owner is decided (onboarding's own card events too).
    async with db.sessions() as session:
        newest = max(
            int(event.payload["_ln_public_cursor"])
            for event in await session.scalars(
                select(EventRow).where(
                    EventRow.owner_id == owner, EventRow.kind.in_(ATTENTION_KINDS)
                )
            )
        )
    assert newest >= max(positions.values())
    assert cursor == newest and decided["after"] and not decided["hang"]
    recorded = await failure(db, "attention_event", str(await event_cursor(db, owner, "hang")))
    assert recorded and recorded.code == "timeout" and recorded.quarantined_at is None


async def event_cursor(db: Database, owner: str, identifier: str) -> int:
    async with db.sessions() as session:
        events = await session.scalars(
            select(EventRow).where(EventRow.owner_id == owner, EventRow.kind == "task.failed")
        )
        return next(event.cursor for event in events if event.payload["id"] == identifier)


@pytest.mark.asyncio
async def test_a_restart_withdraws_running_late_items_it_ended_but_keeps_a_live_gateways(
    task_db: Fixture,
) -> None:
    db, owner, *_ = task_db
    liveness = Liveness()
    stalled = liveness.register(StepSpec("reconcile", 10, 300))
    stalled.registered_at = utcnow() - timedelta(hours=1)
    before = Watchdog(db, liveness, set(), identity="gw-before")
    other = Watchdog(db, liveness, set(), identity="gw-other")
    assert await before.stalled_steps() == 1
    other.episodes["step:reconcile"] = "step:reconcile:other"
    assert await other.alert(
        "gateway_degraded",
        other.episodes["step:reconcile"],
        {"reason_code": "step_stalled", "step": "reconcile", **other.episode("step:reconcile")},
    )
    async with db.sessions() as session, session.begin():
        session.add(GatewayRow(id="gw-before", state="stopped", liveness={}))
        session.add(GatewayRow(id="gw-other", state="running", liveness={}))
    # The restarted gateway runs every step live: nothing it stands behind is late.
    after = Watchdog(db, Liveness(), set(), identity="gw-after")
    assert await after.ended_episodes() == 1
    statuses = {
        item.parameters["gateway"]: item.status
        for item in await system_items(db, owner, "gateway_degraded")
    }
    assert statuses == {"gw-before": "suppressed", "gw-other": "ready"}
    # The live gateway's own episode is still current there.
    assert await other.ended_episodes() == 0


@pytest.mark.asyncio
async def test_a_worker_whose_every_claim_fails_goes_stale_and_is_reported(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db, owner, *_ = task_db
    calls = [0]

    async def broken(*_: Any, **__: Any) -> bool:
        calls[0] += 1
        raise RuntimeError("poison row in the claim query")

    monkeypatch.setattr(service, "dispatch_one", broken)
    gateway = service.Gateway(db, "unused-key", tmp_path, maximum_subagents=0, poll_seconds=0.01)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await gateway.worker_loop(None, "worker-0")
    record = gateway.liveness.steps["worker-0"]
    assert calls[0] == 3 and record.failures == 3
    assert record.last_error == "unexpected_runtime_error" and record.succeeded_at is None
    # A failed claim never counts as liveness, so the worker goes stale and is reported.
    record.registered_at = utcnow() - timedelta(minutes=5)
    assert "worker-0" in gateway.liveness.stalled()
    assert gateway.liveness.snapshot()["ready"] is False
    assert await Watchdog(db, gateway.liveness, set()).stalled_steps() == 1
    degraded = await system_items(db, owner, "gateway_degraded")
    assert [item.parameters["step"] for item in degraded] == ["worker-0"]


def test_the_stall_threshold_covers_one_legitimate_iteration() -> None:
    # A broker outage inside reconcile's own timeout is not a stalled service.
    assert StepSpec("reconcile", 10, 300).stall_after == 310
    assert StepSpec("routines", 5, 120).stall_after == 125
    assert StepSpec("worker-0", 0.5, 0).stall_after == 120


@pytest.mark.asyncio
async def test_quarantine_notices_coalesce_per_kind_and_never_cost_a_critical_alert(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    guard = ItemGuard(db, "routine")

    async def broken() -> None:
        raise RuntimeError("systematic")

    for item in ("routine-a", "routine-b", "routine-c"):
        for _ in range(QUARANTINE_AFTER):
            await expire_backoff(db, "routine")
            await guard.run(item, owner, broken)
    notices = await system_items(db, owner, "maintenance_item_quarantined")
    # One open notice per kind with a count, not three identical items.
    assert len(notices) == 1 and notices[0].parameters["count"] == 3
    assert notices[0].parameters["item_kind"] == "routine"
    async with db.sessions() as session, session.begin():
        emit(
            session,
            owner,
            "trading.approval.updated",
            agent_id=agent,
            payload={"status": "pending"},
        )

    async def poisoned(*_: Any, **__: Any) -> Any:
        raise KeyError("projection bug")

    monkeypatch.setattr(attention, "candidate", poisoned)
    await attention.attention_tick(db, NO_BROKERS, owner)
    for _ in range(QUARANTINE_AFTER - 1):
        await expire_backoff(db, "attention_event")
        await attention.attention_tick(db, NO_BROKERS, owner)
    # The approval alert still reaches the owner under its own code.
    stops = await system_items(db, owner, "approval_required")
    assert len(stops) == 1 and stops[0].status == "ready"
    assert stops[0].importance == "action_required" and stops[0].agent_id == agent
