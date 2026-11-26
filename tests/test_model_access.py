"""Owner-only model failures of background work (P1-08; VISION 11.5, 11.7, Amendment 5).

A background run whose every model candidate fails on a rejected key, spent credit, a
model the key may not use or a model the provider does not have raises one attention
item per provider route and cause, and pushes it. While it stands, due routines of an
agent whose every candidate it covers advance without a run. Saving a new key, or a run
on that route that succeeds, ends it. A transient failure (429) raises nothing.
"""

import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import lonora_agent.executor as executor
import pytest
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage
from lonora_automation.runner import dispatch_routines
from lonora_bus.attention import attention_text
from lonora_contracts.attention import ATTENTION_EVENTS
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import (
    AgentModelPreference,
    AgentModelRecord,
    Capability,
    ModelSelection,
    RoutingPolicy,
)
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import agent_model_key
from lonora_db.attention import attention_view, settle_model_access, withdraw_ended
from lonora_db.client import Database
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.runs import claim_next, create_run
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    RoutineRow,
    RunRow,
    SecretRow,
    SettingRow,
    ThreadRow,
)
from lonora_db.transactions import SettingsRepository
from lonora_gateway.push import PUSH_CODES
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from test_model_context import FixtureCredentials
from test_provider_resilience import Scripted
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
PRIMARY = ModelSelection(provider="openai", model="primary-model")
OTHER = ModelSelection(provider="deepseek", model="other-model")
USER = [ModelMessage(role="user", content="Review gold")]
NO_TOOLS = cast(ToolRegistry, SimpleNamespace(tools={}))


async def routed(db: Database, *backups: ModelSelection) -> None:
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session, "model_routing", RoutingPolicy(unified=PRIMARY).model_dump(mode="json")
        )
        await SettingsRepository().put(
            session,
            "model_backups",
            {"choices": [item.model_dump(mode="json") for item in backups]},
        )


class KeysFor(FixtureCredentials):
    """A key for these providers only: the router passes over the others as unconfigured."""

    def __init__(self, *providers: str) -> None:
        self.providers = set(providers)

    async def resolve(self, provider: str) -> str:
        if provider not in self.providers:
            raise LonoraError("model_not_configured", 409)
        return await super().resolve(provider)


async def routine(db: Database, owner: str, agent: str, thread: str) -> str:
    async with db.sessions() as session, session.begin():
        row = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="Review gold",
            interval_seconds=60,
            next_run_at=utcnow() - timedelta(seconds=5),
        )
        session.add(row)
        await session.flush()
        return row.id


async def due_again(db: Database, routine_id: str) -> None:
    async with db.sessions() as session, session.begin():
        row = await session.get(RoutineRow, routine_id)
        assert row is not None
        row.next_run_at = utcnow() - timedelta(seconds=5)


async def provider_failure(db: Database, *outcomes: Any) -> ModelProviderError:
    """What the real router raises once every candidate failed this way."""
    fake = Scripted(**{"primary-model": list(outcomes)})
    with pytest.raises(ModelProviderError) as caught:
        await fake.router(db).complete(Capability.BACKGROUND, USER, [], choices=[PRIMARY])
    return caught.value


async def chain_failure(
    db: Database, choices: list[ModelSelection], credentials: KeysFor, *outcomes: Any
) -> ModelProviderError:
    """What the real router raises for this chain, with keys only for some providers."""
    fake = Scripted(**{"primary-model": list(outcomes)})
    with pytest.raises(ModelProviderError) as caught:
        await fake.router(db, credentials).complete(
            Capability.BACKGROUND, USER, [], choices=choices
        )
    return caught.value


async def fail_next(db: Database, error: ModelProviderError) -> str:
    """Claim the next queued Run and fail it with ``error``, as the executor does."""
    async with db.sessions() as session, session.begin():
        row = await claim_next(session, "gw-model-access", 120)
        assert row is not None
        lease = Lease(run_id=row.id, owner="gw-model-access", fence=row.lease_fence)
    context = cast(ToolContext, SimpleNamespace(db=db, lease=lease))
    await executor.record_failure(context, NO_TOOLS, error.code, error)
    return lease.run_id


async def items(db: Database, owner: str) -> list[AttentionRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(AttentionRow).where(
                    AttentionRow.owner_id == owner, AttentionRow.code == "model_access_failed"
                )
            )
        )


async def routine_runs(db: Database, routine_id: str) -> list[RunRow]:
    async with db.sessions() as session:
        return [
            run
            for run in await session.scalars(select(RunRow).where(RunRow.trigger == "routine"))
            if run.model_metadata.get("routine_id") == routine_id
        ]


async def save_key(db: Database, owner: str, provider: str) -> None:
    async with db.sessions() as session, session.begin():
        secret = SecretRow(
            owner_id=owner, scope="workspace", name=provider.upper() + "_API_KEY", ciphertext="x"
        )
        session.add(secret)
        await session.flush()
        await SettingsRepository().put(
            session, CONNECTION_SETTING + provider, {"secret_id": secret.id, "url": None}
        )


def test_a_model_access_failure_is_an_owner_event_that_pushes_with_fixed_text() -> None:
    assert ATTENTION_EVENTS["model_access_failed"] == "background_health"
    assert "model_access_failed" in PUSH_CODES
    named = {"reason": "auth", "provider_name": "OpenAI"}
    for locale in ("ar", "en"):
        assert "OpenAI" in attention_text("model_access_failed", locale, named)
        assert attention_text("model_access_failed", locale) != attention_text(
            "internal_update", locale
        )


@pytest.mark.asyncio
async def test_the_router_names_every_candidate_that_failed(task_db: Fixture) -> None:
    db, *_ = task_db
    error = await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    assert error.reason is FailureReason.AUTH
    assert [(provider, model, failed.reason) for provider, model, failed in error.failures] == [
        ("openai", "primary-model", FailureReason.AUTH)
    ]


@pytest.mark.asyncio
async def test_a_rejected_key_raises_one_item_and_the_next_ticks_create_no_run(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    routine_id = await routine(db, owner, agent, thread)
    assert await dispatch_routines(db) == 1
    rejected = await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    await fail_next(db, rejected)
    [item] = await items(db, owner)
    assert item.status == "ready" and item.importance == "action_required"
    assert (item.parameters["provider"], item.parameters["reason"]) == ("openai", "auth")
    # Fixed server text only: the provider's name and the failure family.
    assert set(item.parameters) >= {"provider_name", "route", "credential"}
    async with db.sessions() as session:
        view = await attention_view(session, owner)
    assert [(row["kind"], row["code"]) for row in view] == [
        ("background_health", "model_access_failed")
    ]
    for _ in range(3):
        await due_again(db, routine_id)
        assert await dispatch_routines(db) == 0
    assert len(await routine_runs(db, routine_id)) == 1
    async with db.sessions() as session:
        held = await session.get(RoutineRow, routine_id)
        assert held is not None and held.next_run_at > utcnow()
    # The same cause on the same route raises no second item.
    async with db.sessions() as session, session.begin():
        await create_run(
            session,
            owner,
            RunRequest(thread_id=thread, agent_id=agent, trigger="watch", prompt="Watch gold"),
        )
    await fail_next(db, rejected)
    assert len(await items(db, owner)) == 1


@pytest.mark.asyncio
async def test_saving_a_key_withdraws_the_item_and_the_routine_fires_on_its_next_tick(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    routine_id = await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 0
    await save_key(db, owner, "openai")
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1
    async with db.sessions() as session, session.begin():
        assert await withdraw_ended(session, owner) == 1
    assert [item.status for item in await items(db, owner)] == ["suppressed"]


@pytest.mark.asyncio
async def test_an_agent_on_a_different_working_provider_keeps_running(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    first = await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.BILLING, http_status=402))
    )
    async with db.sessions() as session, session.begin():
        other = AgentRow(owner_id=owner, name="Other desk")
        session.add(other)
        await session.flush()
        desk = ThreadRow(owner_id=owner, agent_id=other.id)
        session.add(desk)
        await session.flush()
        record = AgentModelRecord(
            owner_id=owner, agent_id=other.id, preference=AgentModelPreference(primary=OTHER)
        )
        session.add(
            SettingRow(key=agent_model_key(owner, other.id), payload=record.model_dump(mode="json"))
        )
        other_id, desk_id = other.id, desk.id
    # Working: its provider has a key (one with none could not answer either).
    await save_key(db, owner, "deepseek")
    second = await routine(db, owner, other_id, desk_id)
    await due_again(db, first)
    assert await dispatch_routines(db) == 1
    assert len(await routine_runs(db, first)) == 1
    assert len(await routine_runs(db, second)) == 1


@pytest.mark.asyncio
async def test_a_transient_429_raises_no_item(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    limited = ModelProviderError(FailureReason.RATE_LIMIT, http_status=429, retry_after=1.0)
    await fail_next(db, await provider_failure(db, limited))
    assert await items(db, owner) == []


@pytest.mark.asyncio
async def test_an_owner_message_that_fails_raises_no_item(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        await create_run(
            session, owner, RunRequest(thread_id=thread, agent_id=agent, prompt="Gold now?")
        )
    # The owner is waiting on this one: its own error card already says what failed.
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    assert await items(db, owner) == []


@pytest.mark.asyncio
async def test_a_run_that_succeeds_on_the_route_withdraws_the_item(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    routine_id = await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    # Another model of the same provider answering ends only a per-model cause.
    async with db.sessions() as session, session.begin():
        assert await settle_model_access(session, owner, "openai", "other-model") == 1
    assert [item.status for item in await items(db, owner)] == ["suppressed"]
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1


@pytest.mark.asyncio
async def test_a_missing_model_is_its_own_route(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db,
        await provider_failure(
            db, ModelProviderError(FailureReason.MODEL_NOT_FOUND, http_status=404)
        ),
    )
    [item] = await items(db, owner)
    assert item.parameters["route"] == "openai:primary-model"
    async with db.sessions() as session, session.begin():
        # Another model of the provider answering says nothing about this one.
        assert await settle_model_access(session, owner, "openai", "other-model") == 0
        assert await settle_model_access(session, owner, "openai", "primary-model") == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("LONORA_TASK_TEST_DATABASE_URL"),
    reason="the push cursor needs PostgreSQL (LONORA_TASK_TEST_DATABASE_URL)",
)
async def test_a_model_access_failure_pushes_once_naming_the_provider(task_db: Fixture) -> None:
    from lonora_gateway.push import dispatch_push
    from test_push_sender import CIPHER, PHONE, phone

    class Expo:
        """Accepts every push and records it."""

        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
            self.sent.extend(messages)
            return [{"status": "ok", "id": "ticket"} for _ in messages]

        async def receipts(self, ids: list[str]) -> dict[str, dict[str, Any]]:
            return {}

    db, owner, agent, thread = task_db
    await routed(db)
    await phone(db, owner, PHONE, "ExponentPushToken[phone000000000001]")
    expo = Expo()
    # The first pass places the cursor at the end of the stream.
    assert await dispatch_push(db, owner, CIPHER, expo) == 0
    await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    assert await dispatch_push(db, owner, CIPHER, expo) == 1
    assert await dispatch_push(db, owner, CIPHER, expo) == 0
    body = expo.sent[0]["body"]
    assert "OpenAI" in body
    assert body == attention_text(
        "model_access_failed", "ar", {"reason": "auth", "provider_name": "OpenAI"}
    )


@pytest.mark.asyncio
async def test_a_backup_with_no_key_does_not_keep_the_routine_failing(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    monkeypatch.delenv("LONORA_DEEPSEEK_API_KEY", raising=False)
    await routed(db, OTHER)
    routine_id = await routine(db, owner, agent, thread)
    assert await dispatch_routines(db) == 1
    # The router passes over the backup, which has no key, and the primary key is rejected.
    error = await chain_failure(
        db,
        [PRIMARY, OTHER],
        KeysFor("openai"),
        ModelProviderError(FailureReason.AUTH, http_status=401),
    )
    assert [(provider, failed.reason) for provider, _, failed in error.failures] == [
        ("openai", FailureReason.AUTH),
        ("deepseek", FailureReason.NOT_CONFIGURED),
    ]
    await fail_next(db, error)
    assert len(await items(db, owner)) == 1
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 0
    assert len(await routine_runs(db, routine_id)) == 1
    # A key saved for the backup gives the routine a model that may answer.
    await save_key(db, owner, "deepseek")
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1


@pytest.mark.asyncio
async def test_a_model_past_the_routers_cap_does_not_keep_the_routine_failing(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    # Six distinct models of one provider (a repeat takes no place), then a seventh that the
    # router never tries although its provider has a key.
    backups = [ModelSelection(provider="openai", model=f"backup-{n}") for n in range(5)]
    await routed(db, PRIMARY, *backups, OTHER)
    await save_key(db, owner, "deepseek")
    routine_id = await routine(db, owner, agent, thread)
    assert await dispatch_routines(db) == 1
    error = await chain_failure(
        db,
        [PRIMARY, *backups, OTHER],
        KeysFor("openai", "deepseek"),
        ModelProviderError(FailureReason.AUTH, http_status=401),
    )
    assert {provider for provider, _, _ in error.failures} == {"openai"}
    assert len(error.failures) == 6
    await fail_next(db, error)
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 0
    assert len(await routine_runs(db, routine_id)) == 1


@pytest.mark.asyncio
async def test_a_held_one_shot_stays_due_and_fires_once_released(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    due = utcnow() - timedelta(seconds=5)
    async with db.sessions() as session, session.begin():
        shot = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="Check gold at 9",
            run_at=due,
            next_run_at=due,
        )
        session.add(shot)
        await session.flush()
        shot_id = shot.id
    assert await dispatch_routines(db) == 0
    async with db.sessions() as session:
        held = await session.get(RoutineRow, shot_id)
        assert held is not None and held.enabled and held.last_run_at is None
    await save_key(db, owner, "openai")
    assert await dispatch_routines(db) == 1
    [run] = await routine_runs(db, shot_id)
    # It runs late, and its run knows when it was due.
    assert run.model_metadata["scheduled_for"] == due.isoformat()


@pytest.mark.asyncio
async def test_a_held_tick_counts_as_skipped(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    routine_id = await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db, await provider_failure(db, ModelProviderError(FailureReason.AUTH, http_status=401))
    )
    for _ in range(2):
        await due_again(db, routine_id)
        assert await dispatch_routines(db) == 0
    async with db.sessions() as session:
        held = await session.get(RoutineRow, routine_id)
        assert held is not None and held.skipped_occurrences == 2
    await save_key(db, owner, "openai")
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1
    runs = sorted(await routine_runs(db, routine_id), key=lambda run: run.created_at)
    assert runs[-1].model_metadata["skipped_occurrences"] == 2


async def pass_time(db: Database, minutes: int) -> None:
    """Move every item and run back by ``minutes``, as if that much time had passed."""
    async with db.sessions() as session, session.begin():
        for table in (AttentionRow, RunRow):
            for row in await session.scalars(select(table)):
                row.created_at -= timedelta(minutes=minutes)


@pytest.mark.asyncio
async def test_a_held_routine_is_tried_again_after_a_growing_wait(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    routine_id = await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    spent = await provider_failure(db, ModelProviderError(FailureReason.BILLING, http_status=402))
    await fail_next(db, spent)
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 0
    # The owner may top up the account at the provider, which Lonora cannot see: a quarter
    # of an hour after the item, one routine run goes through to try again.
    await pass_time(db, 16)
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1
    # It fails the same way: no second item, and the next try waits twice as long.
    await fail_next(db, spent)
    assert [item.status for item in await items(db, owner)] == ["ready"]
    await pass_time(db, 29)
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 0
    await pass_time(db, 2)
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1
    assert len(await routine_runs(db, routine_id)) == 3
    # That try succeeds (the account was topped up): the item ends and routines fire again.
    async with db.sessions() as session, session.begin():
        answered = await claim_next(session, "gw-model-access", 120)
        assert answered is not None
        answered.status = "completed"
        assert await settle_model_access(session, owner, "openai", "primary-model") == 1
    await due_again(db, routine_id)
    assert await dispatch_routines(db) == 1


@pytest.mark.asyncio
async def test_a_missing_model_ends_once_no_agent_would_try_it(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    await routed(db)
    await routine(db, owner, agent, thread)
    await dispatch_routines(db)
    await fail_next(
        db,
        await provider_failure(
            db, ModelProviderError(FailureReason.MODEL_NOT_FOUND, http_status=404)
        ),
    )
    assert len(await items(db, owner)) == 1
    # The owner chooses another model, as the item asks.
    newer = ModelSelection(provider="openai", model="newer-model")
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session, "model_routing", RoutingPolicy(unified=newer).model_dump(mode="json")
        )
    async with db.sessions() as session:
        assert [row["code"] for row in await attention_view(session, owner)] == []
    async with db.sessions() as session, session.begin():
        assert await withdraw_ended(session, owner) == 1
    assert [item.status for item in await items(db, owner)] == ["suppressed"]
