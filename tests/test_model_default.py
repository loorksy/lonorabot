"""The no-model state: a fresh install answers, and says the truth when it cannot.

With a provider key and no routing, the router chooses that provider's default model
from Lonora's list (VISION 12.4) and records it as the routing; no provider is asked
for its models, except the owner's own endpoint, whose first listed model is taken. A
key the provider rejects is passed over for the next provider's.
With nothing to choose from it raises ``model_not_configured`` (never an outage), and
the replies that failed for that reason are queued again, in order, once the owner
connects a model.
"""

from typing import Any

import httpx
import pytest
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import Capability, ModelSelection, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.run_retry import retry_unconfigured
from lonora_db.schema import MessageRow, RunRow, SettingRow
from lonora_providers import default_model
from lonora_providers.catalog import list_source, listed_models, read_catalog
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.default_model import DEFAULT_MODELS
from lonora_providers.registry import OWNER_ENDPOINT, PROVIDERS
from lonora_providers.router import GlobalModelRouter
from lonora_providers.routing_policy import read_policy
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from test_model_context import router_db as router_db
from test_model_context import settings
from test_task_runtime import task_db as task_db

USER = [ModelMessage(role="user", content="مرحبا")]
ENDPOINT = "https://llm.example.test/v1"


class Keys(ProviderCredentials):
    """Provider keys of a fresh install: only the named providers have one."""

    def __init__(self, *providers: str) -> None:
        self.providers = providers

    async def resolve(self, provider: str) -> str:
        if provider not in self.providers:
            raise LonoraError("model_not_configured", 409)
        return "fixture-not-a-real-key"

    async def connection(self, provider: str) -> tuple[str, str | None]:
        return await self.resolve(provider), ENDPOINT if provider in OWNER_ENDPOINT else None


class Provider:
    """One provider's account: it answers turns, and the owner's endpoint lists its
    models (or answers a failure). ``discovered`` counts every request for a list."""

    def __init__(
        self, provider: str, models: list[str] | None = None, failure: LonoraError | None = None
    ):
        self.provider, self.models, self.failure = provider, models or [], failure
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

    def factory(provider: str, _: str, base_url: str | None = None) -> ModelAdapter:
        return by_name[provider]

    return GlobalModelRouter(db, keys, factory)


def test_each_provider_defaults_to_a_strong_model_of_the_list() -> None:
    # The owner's choice of defaults (VISION Amendment 4, M4), one per fixed provider.
    assert DEFAULT_MODELS == {
        "openai": "gpt-6.2-sol",
        "openai_chatgpt": "gpt-6.1-sol",
        "anthropic": "claude-sonnet-5-5",
        "deepseek": "deepseek-v4-pro",
        "zai": "glm-5.3",
        "openrouter": "anthropic/claude-sonnet-5.5",
    }
    assert set(DEFAULT_MODELS) == set(PROVIDERS) - OWNER_ENDPOINT
    for provider, model in DEFAULT_MODELS.items():
        assert model in {item.id for item in listed_models(provider)}, (provider, model)


@pytest.mark.asyncio
async def test_a_fresh_install_with_a_key_answers_and_records_its_choice(
    router_db: Database,
) -> None:
    # Voice routes the owner already set stay as they are.
    voice = {"stt": {"provider": "openai", "model": "whisper-1"}}
    await settings(router_db, {"model_routing": {"mode": "unified", "routes": voice}})
    openai, zai = Provider("openai"), Provider("zai")
    route = router(router_db, Keys("openai", "zai"), openai, zai)
    reply, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert reply.text and selection == ModelSelection(provider="openai", model="gpt-6.2-sol")
    assert openai.asked == ["gpt-6.2-sol"] and zai.asked == []
    # The choice is the routing, so Settings show it and the next request reads it.
    policy = await read_policy(router_db)
    assert policy.unified == selection and policy.mode == "unified"
    assert policy.routes[Capability.STT].model == "whisper-1"
    await route.complete(Capability.BACKGROUND, USER, [])
    # No provider was asked for its models, and none of their lists was stored: the
    # catalog is Lonora's list.
    assert openai.discovered == 0 and zai.discovered == 0
    assert [item.id for item in await read_catalog(router_db, "openai")] == [
        item.id for item in listed_models("openai")
    ]
    async with router_db.sessions() as session:
        assert await session.get(SettingRow, "catalog:openai") is None


@pytest.mark.asyncio
async def test_a_deepseek_key_chooses_its_default_with_the_lists_window(
    router_db: Database,
) -> None:
    """A fresh install with only a DeepSeek key (production, 2026-11): a model is chosen,
    never "not configured", and it is sized by the window the list states."""
    deepseek = Provider("deepseek")
    route = router(router_db, Keys("deepseek"), deepseek)
    reply, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert reply.text
    assert selection == ModelSelection(provider="deepseek", model="deepseek-v4-pro")
    assert deepseek.asked == ["deepseek-v4-pro"] and deepseek.discovered == 0
    limits = await route.context_limits(Capability.CONVERSATION)
    assert limits.window == 1_000_000 and limits.capacity_source == list_source()


@pytest.mark.asyncio
async def test_providers_are_taken_in_registry_order_and_only_a_listed_default_is_chosen(
    router_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    accounts = (Provider("zai"), Provider("anthropic"))
    _, selection = await router(router_db, Keys("zai", "anthropic"), *accounts).complete(
        Capability.CONVERSATION, USER, []
    )
    assert selection == ModelSelection(provider="anthropic", model="claude-sonnet-5-5")
    # A default the list no longer holds is never chosen: the next provider's is.
    await settings(router_db, {"model_routing": {}})
    monkeypatch.setitem(DEFAULT_MODELS, "anthropic", "claude-sonnet-unlisted")
    _, selection = await router(router_db, Keys("zai", "anthropic"), *accounts).complete(
        Capability.CONVERSATION, USER, []
    )
    assert selection == ModelSelection(provider="zai", model="glm-5.3")


class KeyStatuses:
    """Real adapters on fake providers, each answering its key check with a status."""

    def __init__(self, **statuses: int) -> None:
        self.statuses = statuses
        self.seen: list[tuple[str, str, str]] = []

    def __call__(self, provider: str, key: str, base_url: str | None = None) -> ModelAdapter:
        def answer(request: httpx.Request) -> httpx.Response:
            self.seen.append((provider, request.method, request.url.path))
            return httpx.Response(self.statuses[provider], json={"data": [{"id": "unlisted"}]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
        return PROVIDERS[provider](key, client)


@pytest.mark.asyncio
async def test_a_rejected_key_is_passed_over_for_the_next_providers_working_one(
    router_db: Database,
) -> None:
    # A stale OpenAI key (an old LONORA_OPENAI_API_KEY) never takes the route from a
    # working Anthropic key.
    statuses = KeyStatuses(openai=401, anthropic=200)
    keys = Keys("openai", "anthropic")
    chosen = await default_model.choose_default_model(router_db, keys, statuses)
    assert chosen == ModelSelection(provider="anthropic", model="claude-sonnet-5-5")
    assert (await read_policy(router_db)).unified == chosen
    # One status-only request per key; nothing the providers list is kept.
    assert statuses.seen == [("openai", "GET", "/v1/models"), ("anthropic", "GET", "/v1/models")]
    async with router_db.sessions() as session:
        assert await session.get(SettingRow, "catalog:anthropic") is None


@pytest.mark.asyncio
async def test_a_key_that_could_not_be_checked_is_used(router_db: Database) -> None:
    statuses = KeyStatuses(openai=503, anthropic=200)
    chosen = await default_model.choose_default_model(
        router_db, Keys("openai", "anthropic"), statuses
    )
    assert chosen == ModelSelection(provider="openai", model="gpt-6.2-sol")
    assert statuses.seen == [("openai", "GET", "/v1/models")]


@pytest.mark.asyncio
async def test_only_rejected_keys_choose_nothing_and_say_the_key_was_rejected(
    router_db: Database,
) -> None:
    statuses = KeyStatuses(openai=401, anthropic=403)
    with pytest.raises(ModelProviderError) as raised:
        await default_model.choose_default_model(router_db, Keys("openai", "anthropic"), statuses)
    assert raised.value.code == "model_credentials_rejected"
    assert (await read_policy(router_db)).unified is None


@pytest.mark.asyncio
async def test_without_a_key_or_a_listed_model_the_state_is_not_configured(
    router_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(DEFAULT_MODELS, "openai", "gpt-unlisted")
    for route in (
        router(router_db, Keys()),
        router(router_db, Keys("openai"), Provider("openai")),
        router(router_db, Keys("openai_compatible"), Provider("openai_compatible")),
    ):
        with pytest.raises(LonoraError) as raised:
            await route.complete(Capability.CONVERSATION, USER, [])
        assert raised.value.code == "model_not_configured"
        with pytest.raises(LonoraError) as raised:
            await route.context_limits(Capability.CONVERSATION)
        assert raised.value.code == "model_not_configured"
    assert (await read_policy(router_db)).unified is None


@pytest.mark.asyncio
async def test_the_owners_endpoint_answers_with_the_first_model_it_lists(
    router_db: Database,
) -> None:
    endpoint = Provider("openai_compatible", ["llama-4", "qwen-4"])
    route = router(router_db, Keys("openai_compatible"), endpoint)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection == ModelSelection(provider="openai_compatible", model="llama-4")
    assert endpoint.discovered == 1
    # Its own list is its catalog: the owner's models.
    assert [item.id for item in await read_catalog(router_db, "openai_compatible")] == [
        "llama-4",
        "qwen-4",
    ]


@pytest.mark.asyncio
async def test_an_unreachable_endpoint_is_reported_as_unreachable_not_as_unconfigured(
    router_db: Database,
) -> None:
    outage = ModelProviderError(FailureReason.CONNECTION)
    down = Provider("openai_compatible", failure=outage)
    route = router(router_db, Keys("openai_compatible"), down)
    with pytest.raises(ModelProviderError) as raised:
        await route.complete(Capability.CONVERSATION, USER, [])
    assert raised.value.code == "model_provider_unavailable"
    assert (await read_policy(router_db)).unified is None
    # A connected provider answers before the endpoint is asked at all.
    down = Provider("openai_compatible", failure=outage)
    route = router(router_db, Keys("zai", "openai_compatible"), Provider("zai"), down)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection.provider == "zai" and down.discovered == 0


@pytest.mark.asyncio
async def test_only_a_text_request_chooses_and_a_read_never_does(router_db: Database) -> None:
    openai = Provider("openai")
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
    assert openai.asked == [] and (await read_policy(router_db)).unified is None


@pytest.mark.asyncio
async def test_the_owners_own_models_are_never_replaced(router_db: Database) -> None:
    chosen = ModelSelection(provider="zai", model="glm-4.7")
    await settings(router_db, {"model_backups": {"choices": [chosen.model_dump(mode="json")]}})
    openai, zai = Provider("openai"), Provider("zai")
    route = router(router_db, Keys("openai", "zai"), openai, zai)
    _, selection = await route.complete(Capability.CONVERSATION, USER, [])
    assert selection == chosen and openai.asked == []
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
async def test_an_agent_in_full_is_not_answered_late_by_itself(
    task_db: tuple[Database, str, str, str],
) -> None:
    """An agent in Full that is not paused trades on its own like one holding a signed
    grant (``agents_on_their_own``): its failed reply waits for the owner's own retry."""
    from lonora_db import run_retry
    from lonora_db.agent_permissions import initial_permission
    from lonora_db.schema import AgentRow

    db, owner, agent, thread = task_db
    late = await failed(db, thread, agent, 1)
    async with db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent)
        assert row is not None
        row.trading_mode = "full"
        # Not held at the old ladder's "No trading", which refuses every send.
        await initial_permission(session, owner, agent, "supervised")
    async with db.sessions() as session, session.begin():
        assert await retry_unconfigured(session, owner) == []
        assert (await run_retry.retry_run(session, owner, late)).status == "queued"


@pytest.mark.asyncio
async def test_custom_routes_are_never_filled_in_and_a_fruitless_search_is_not_repeated(
    router_db: Database,
) -> None:
    custom = {"mode": "custom", "routes": {"conversation": {"provider": "zai", "model": "glm-5.3"}}}
    await settings(router_db, {"model_routing": custom})
    openai = Provider("openai")
    route = router(router_db, Keys("openai", "zai"), openai, Provider("zai"))
    with pytest.raises(LonoraError):
        await route.complete(Capability.VISION, USER, [])
    assert openai.asked == []
    assert (await read_policy(router_db)).model_dump(mode="json")["unified"] is None
    # An endpoint that lists nothing is asked once, not on every request.
    await settings(router_db, {"model_routing": {}})
    empty = Provider("openai_compatible")
    route = router(router_db, Keys("openai_compatible"), empty)
    for _ in range(3):
        with pytest.raises(LonoraError):
            await route.context_limits(Capability.CONVERSATION)
        with pytest.raises(LonoraError):
            await route.complete(Capability.CONVERSATION, USER, [])
    assert empty.discovered == 1


@pytest.mark.asyncio
async def test_concurrent_first_requests_choose_once(
    router_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    chosen: list[ModelSelection | None] = []
    choose = default_model.choose_default_model

    async def counted(*args: Any) -> ModelSelection | None:
        chosen.append(await choose(*args))
        return chosen[-1]

    monkeypatch.setattr("lonora_providers.router.choose_default_model", counted)
    endpoint = Provider("openai_compatible", ["llama-4"])
    route = router(router_db, Keys("openai_compatible"), endpoint)
    await asyncio.gather(*(route.complete(Capability.CONVERSATION, USER, []) for _ in range(5)))
    assert len(chosen) == 1 and endpoint.discovered == 1


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
