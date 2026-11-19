"""The no-model state: a fresh install answers, and says the truth when it cannot.

With a provider key and no routing, the router chooses a model the provider's own
catalog lists, by a fixed preference, and records it as the routing. With nothing to
choose from it raises ``model_not_configured`` (never an outage), and the replies that
failed for that reason are queued again, in order, once the owner connects a model.
"""

from typing import Any

import pytest
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import Capability, ModelSelection, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.run_retry import retry_unconfigured
from lonora_db.schema import MessageRow, RunRow
from lonora_providers.catalog import read_catalog
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.default_model import preferred_model
from lonora_providers.router import GlobalModelRouter
from lonora_providers.routing_policy import read_policy
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from test_model_context import router_db as router_db
from test_model_context import settings
from test_task_runtime import task_db as task_db

USER = [ModelMessage(role="user", content="مرحبا")]


class Keys(ProviderCredentials):
    """Provider keys of a fresh install: only the named providers have one."""

    def __init__(self, *providers: str) -> None:
        self.providers = providers

    async def resolve(self, provider: str) -> str:
        if provider not in self.providers:
            raise LonoraError("model_not_configured", 409)
        return "fixture-not-a-real-key"


class Provider:
    """One provider's account: the models its catalog lists, or the failure it answers."""

    def __init__(self, provider: str, models: list[str], failure: LonoraError | None = None):
        self.provider, self.models, self.failure = provider, models, failure
        self.discovered = 0
        self.asked: list[str] = []

    async def complete(
        self, model: str, messages: list[ModelMessage], tools: list[ToolDefinition], **_: Any
    ) -> ModelReply:
        self.asked.append(model)
        return ModelReply(text="مرحباً. كيف أساعدك؟")

    async def discover(self) -> list[ModelDescriptor]:
        self.discovered += 1
        if self.failure:
            raise self.failure
        return [
            ModelDescriptor(id=model, provider=self.provider, name=model, source="fixture")  # type: ignore[arg-type]
            for model in self.models
        ]

    async def close(self) -> None:
        return None


def router(db: Database, keys: Keys, *accounts: Provider) -> GlobalModelRouter:
    by_name = {account.provider: account for account in accounts}

    def factory(provider: str, _: str) -> ModelAdapter:
        return by_name[provider]

    return GlobalModelRouter(db, keys, factory)


def test_the_preference_picks_only_models_the_catalog_lists() -> None:
    families = ("claude-sonnet-5", "claude-sonnet-4-5")
    # A dated snapshot is the family; the newest snapshot wins.
    assert (
        preferred_model(
            [
                "claude-opus-4-5-20251101",
                "claude-sonnet-4-5-20250929",
                "claude-sonnet-4-5-20250801",
            ],
            families,
        )
        == "claude-sonnet-4-5-20250929"
    )
    # The exact id wins over its snapshots, and an earlier family over a later one.
    assert preferred_model(["gpt-5-mini-2025-08-07", "gpt-5-mini"], ("gpt-5-mini",)) == "gpt-5-mini"
    assert preferred_model(["claude-sonnet-4-5", "claude-sonnet-5"], families) == "claude-sonnet-5"
    # Another model that only shares the prefix is not the family.
    assert preferred_model(["gpt-5-mini", "gpt-5-codex", "gpt-5.4"], ("gpt-5",)) is None
    assert preferred_model([], families) is None


@pytest.mark.asyncio
async def test_a_fresh_install_with_a_key_answers_and_records_its_choice(
    router_db: Database,
) -> None:
    # Voice routes the owner already set stay as they are.
    voice = {"stt": {"provider": "openai", "model": "whisper-1"}}
    await settings(router_db, {"model_routing": {"mode": "unified", "routes": voice}})
    openai = Provider("openai", ["whisper-1", "gpt-5-mini", "gpt-5"])
    zai = Provider("zai", ["glm-4.6"])
    route = router(router_db, Keys("openai", "zai"), openai, zai)
    reply, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert reply.text and selection == ModelSelection(provider="openai", model="gpt-5-mini")
    assert openai.asked == ["gpt-5-mini"] and zai.discovered == 0
    # The choice is the routing, so Settings show it and the next request reads it.
    policy = await read_policy(router_db)
    assert policy.unified == selection and policy.mode == "unified"
    assert policy.routes[Capability.STT].model == "whisper-1"
    assert [item.id for item in await read_catalog(router_db, "openai")] == openai.models
    await route.complete(Capability.BACKGROUND, USER, [])
    assert openai.discovered == 1


@pytest.mark.asyncio
async def test_a_deepseek_key_chooses_a_model_its_current_catalog_lists(
    router_db: Database,
) -> None:
    """A fresh install with only a DeepSeek key, whose catalog lists the current ids
    (seen in production, 2026-11): a model is chosen, never "not configured"."""
    from lonora_providers.model_windows import family_output, family_window

    deepseek = Provider("deepseek", ["deepseek-flash", "deepseek-v4-pro"])
    route = router(router_db, Keys("deepseek"), deepseek)
    reply, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert reply.text
    assert selection == ModelSelection(provider="deepseek", model="deepseek-v4-pro")
    assert deepseek.asked == ["deepseek-v4-pro"]
    # A catalog with only the other id still chooses it.
    assert preferred_model(["deepseek-flash"], ("deepseek-v4-pro", "deepseek-flash")) == (
        "deepseek-flash"
    )
    # Their windows are not documented here: they stay unknown, so the policy's limits
    # apply until the provider states one (never a guessed number).
    for model in ("deepseek-flash", "deepseek-v4-pro"):
        assert family_window(model) is None and family_output(model) is None


@pytest.mark.asyncio
async def test_the_next_provider_is_used_when_the_first_lists_no_preferred_model(
    router_db: Database,
) -> None:
    openai = Provider("openai", ["text-embedding-3-small"])
    zai = Provider("zai", ["glm-4.6", "glm-4.5v"])
    route = router(router_db, Keys("openai", "zai"), openai, zai)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection == ModelSelection(provider="zai", model="glm-4.6")


@pytest.mark.asyncio
async def test_without_a_key_or_a_known_model_the_state_is_not_configured(
    router_db: Database,
) -> None:
    for route in (
        router(router_db, Keys()),
        router(router_db, Keys("openai"), Provider("openai", ["text-embedding-3-small"])),
    ):
        with pytest.raises(LonoraError) as raised:
            await route.complete(Capability.CONVERSATION, USER, [])
        assert raised.value.code == "model_not_configured"
        with pytest.raises(LonoraError) as raised:
            await route.context_limits(Capability.CONVERSATION)
        assert raised.value.code == "model_not_configured"
    assert (await read_policy(router_db)).unified is None


@pytest.mark.asyncio
async def test_an_unreachable_provider_is_reported_as_unreachable_not_as_unconfigured(
    router_db: Database,
) -> None:
    outage = ModelProviderError(FailureReason.CONNECTION)
    route = router(router_db, Keys("openai"), Provider("openai", [], outage))
    with pytest.raises(ModelProviderError) as raised:
        await route.complete(Capability.CONVERSATION, USER, [])
    assert raised.value.code == "model_provider_unavailable"
    assert (await read_policy(router_db)).unified is None
    # A provider that answers is still used when another one is down.
    zai = Provider("zai", ["glm-4.6"])
    route = router(router_db, Keys("openai", "zai"), Provider("openai", [], outage), zai)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection.provider == "zai"


@pytest.mark.asyncio
async def test_only_a_text_request_chooses_and_a_read_never_does(router_db: Database) -> None:
    openai = Provider("openai", ["gpt-5-mini"])
    route = router(router_db, Keys("openai"), openai)
    # Reading the route (the model card, model_list) changes nothing.
    with pytest.raises(LonoraError) as raised:
        await route.route(Capability.CONVERSATION)
    assert raised.value.code == "model_not_configured"
    # Speech keeps its own routes: no text model is chosen for it.
    with pytest.raises(LonoraError) as raised:
        await route.complete(Capability.STT, USER, [])
    assert raised.value.code == "model_not_configured"
    # A consultation names its own models.
    with pytest.raises(LonoraError):
        await route.complete(Capability.CONVERSATION, USER, [], choices=[])
    assert openai.discovered == 0 and (await read_policy(router_db)).unified is None


@pytest.mark.asyncio
async def test_the_owners_own_models_are_never_replaced(router_db: Database) -> None:
    chosen = ModelSelection(provider="zai", model="glm-4.6")
    await settings(router_db, {"model_backups": {"choices": [chosen.model_dump(mode="json")]}})
    openai, zai = Provider("openai", ["gpt-5-mini"]), Provider("zai", ["glm-4.6"])
    route = router(router_db, Keys("openai", "zai"), openai, zai)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection == chosen and openai.discovered == 0
    assert (await read_policy(router_db)) == RoutingPolicy()


# --- Replies that failed for lack of a model are answered once one is connected -------


async def failed(
    db: Database,
    thread: str,
    agent: str,
    seq: int,
    *,
    code: str = "model_not_configured",
    retry_of: str | None = None,
) -> str:
    async with db.sessions() as session, session.begin():
        if retry_of is None:
            session.add(MessageRow(thread_id=thread, seq=seq, role="user", content="مرحبا"))
        run = RunRow(
            thread_id=thread,
            agent_id=agent,
            trigger="user",
            input_seq=seq,
            status="failed",
            error_code=code,
            model_metadata={"retry_of": retry_of} if retry_of else {},
        )
        if retry_of:
            run.id = stable_id(retry_of, "run-retry")
        session.add(run)
    return run.id


@pytest.mark.asyncio
async def test_every_reply_that_failed_for_lack_of_a_model_is_queued_again_in_order(
    task_db: tuple[Database, str, str, str],
) -> None:
    """The production case: two greetings failed, the owner tapped retry on both, both
    failed again, and only the second one was ever answered."""
    db, owner, agent, thread = task_db
    first = await failed(db, thread, agent, 1)
    second = await failed(db, thread, agent, 2)
    first_again = await failed(db, thread, agent, 1, retry_of=first)
    # A reply that failed for another reason keeps its own card and its own retry.
    outage = await failed(db, thread, agent, 3, code="model_provider_unavailable")
    async with db.sessions() as session, session.begin():
        retried = await retry_unconfigured(session, owner)
        assert [(run.input_seq, run.model_metadata["retry_of"]) for run in retried] == [
            (1, first_again),
            (2, second),
        ]
        assert all(run.status == "queued" and run.trigger == "user" for run in retried)
    async with db.sessions() as session:
        queued = list(
            await session.scalars(
                select(RunRow).where(RunRow.status == "queued").order_by(RunRow.created_at)
            )
        )
        # The worker claims a conversation's Runs oldest first: the first message first.
        assert [run.input_seq for run in queued] == [1, 2]
        assert await session.get(RunRow, stable_id(outage, "run-retry")) is None
    # Saving the settings again queues nothing twice.
    async with db.sessions() as session, session.begin():
        assert await retry_unconfigured(session, owner) == []


@pytest.mark.asyncio
async def test_a_failure_the_conversation_moved_past_is_not_answered_late(
    task_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = task_db
    await failed(db, thread, agent, 1)
    async with db.sessions() as session, session.begin():
        session.add(MessageRow(thread_id=thread, seq=2, role="user", content="مين انت"))
        session.add(
            RunRow(
                thread_id=thread, agent_id=agent, trigger="user", input_seq=2, status="completed"
            )
        )
    async with db.sessions() as session, session.begin():
        assert await retry_unconfigured(session, owner) == []


@pytest.mark.asyncio
async def test_an_agent_trading_on_its_own_is_not_answered_late_by_itself(
    task_db: tuple[Database, str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A late instruction to an agent holding a signed grant could move money unasked:
    its failed reply keeps its card, and the owner's own retry still works."""
    from lonora_db import run_retry

    db, owner, agent, thread = task_db
    late = await failed(db, thread, agent, 1)

    async def granted(session: object, owner_id: str) -> set[str]:
        return {agent}

    monkeypatch.setattr(run_retry, "agents_on_their_own", granted)
    async with db.sessions() as session, session.begin():
        assert await retry_unconfigured(session, owner) == []
        assert (await run_retry.retry_run(session, owner, late)).status == "queued"


@pytest.mark.asyncio
async def test_custom_routes_are_never_filled_in_and_a_fruitless_search_is_not_repeated(
    router_db: Database,
) -> None:
    custom = {"mode": "custom", "routes": {"conversation": {"provider": "zai", "model": "glm-4.6"}}}
    await settings(router_db, {"model_routing": custom})
    openai = Provider("openai", ["gpt-5-mini"])
    route = router(router_db, Keys("openai", "zai"), openai, Provider("zai", ["glm-4.6"]))
    with pytest.raises(LonoraError):
        await route.complete(Capability.VISION, USER, [])
    assert openai.discovered == 0
    assert (await read_policy(router_db)).model_dump(mode="json")["unified"] is None
    # A key whose catalog lists nothing preferred is asked once, not on every request.
    await settings(router_db, {"model_routing": {}})
    empty = Provider("openai", ["text-embedding-3-small"])
    route = router(router_db, Keys("openai"), empty)
    for _ in range(3):
        with pytest.raises(LonoraError):
            await route.context_limits(Capability.CONVERSATION)
        with pytest.raises(LonoraError):
            await route.complete(Capability.CONVERSATION, USER, [])
    assert empty.discovered == 1


@pytest.mark.asyncio
async def test_concurrent_first_requests_choose_once(router_db: Database) -> None:
    import asyncio

    openai = Provider("openai", ["gpt-5-mini"])
    route = router(router_db, Keys("openai"), openai)
    await asyncio.gather(*(route.complete(Capability.CONVERSATION, USER, []) for _ in range(5)))
    assert openai.discovered == 1


@pytest.mark.asyncio
async def test_an_old_failure_is_not_answered_when_a_key_is_saved(
    task_db: tuple[Database, str, str, str],
) -> None:
    from datetime import timedelta

    from lonora_contracts.domain import utcnow

    db, owner, agent, thread = task_db
    old = await failed(db, thread, agent, 1)
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, old)
        assert run is not None
        run.created_at = utcnow() - timedelta(days=3)
    async with db.sessions() as session, session.begin():
        assert await retry_unconfigured(session, owner) == []
