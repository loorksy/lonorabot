"""Real routing/HTTP admission, without model credentials or external effects."""

import hashlib
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from lonora_adapter_kit.context import context_blocks, govern_context, token_estimate
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ToolCall, ToolDefinition
from lonora_adapters.models.anthropic import AnthropicAdapter
from lonora_adapters.models.deepseek import DeepSeekAdapter
from lonora_adapters.models.openai import OpenAIAdapter
from lonora_adapters.models.openrouter import OpenRouterAdapter
from lonora_adapters.models.zai import ZaiAdapter
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_context import ModelContextPolicy
from lonora_contracts.model_routing import Capability, ModelSelection, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import Base
from lonora_db.transactions import SettingsRepository
from lonora_providers.context import prepare_context
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.router import GlobalModelRouter
from pydantic import ValidationError


def descriptor(window: int) -> ModelDescriptor:
    return ModelDescriptor(
        id="fixture-model",
        provider="openai",
        name="Fixture",
        context_window=window,
        source="fixture:catalog",
    )


def exchange(content: str = "{}") -> list[ModelMessage]:
    return [
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(
                    id="financial-receipt", name="trade_read", arguments={"operation_id": "op-42"}
                )
            ],
        ),
        ModelMessage(role="tool", tool_call_id="financial-receipt", content=content),
    ]


@pytest.mark.parametrize(
    "old_text", ["old market evidence " * 700, "تحليل سابق للسوق " * 700], ids=["english", "arabic"]
)
def test_latest_instruction_and_exchange_survive_and_originals_are_immutable(old_text: str) -> None:
    messages = [
        ModelMessage(role="system", content="Authoritative controls remain in the server."),
        ModelMessage(role="user", content="Earlier question"),
        ModelMessage(role="assistant", content=old_text),
        ModelMessage(role="user", content="Latest steering: inspect only; do not trade."),
        *exchange(
            json.dumps(
                {
                    "ok": True,
                    "status": "confirmed",
                    "operation_id": "op-42",
                    "symbol": "XAUUSDm",
                    "data": "old candles " * 1500,
                }
            )
        ),
    ]
    original = [m.model_dump() for m in messages]
    result = prepare_context(messages, [], descriptor(5000), ModelContextPolicy())
    context_blocks([m for m in result.messages if m.role != "system"])
    assert result.messages[1].content == "Latest steering: inspect only; do not trade."
    observation = json.loads(result.messages[-1].content)
    assert observation["result_omitted"]
    assert observation["ok"] and observation["operation_id"] == "op-42"
    assert observation["status"] == "confirmed" and observation["symbol"] == "XAUUSDm"
    assert result.diagnostics["estimated_input_tokens"] <= result.diagnostics["input_limit"]
    assert [m.model_dump() for m in messages] == original


@pytest.mark.parametrize("role", ["system", "user"])
def test_mandatory_context_is_never_silently_truncated(role: str) -> None:
    message = ModelMessage.model_validate({"role": role, "content": "important " * 4000})
    with pytest.raises(LonoraError, match="context_limit_exceeded"):
        prepare_context([message], [], descriptor(5000), ModelContextPolicy())


def test_images_and_schema_budgets_and_unknown_capacity_are_explicit() -> None:
    request = [
        ModelMessage(
            role="user", content="Inspect this chart", images=["data:image/png;base64,AA=="]
        )
    ]
    policy = ModelContextPolicy(image_tokens=8192)
    with pytest.raises(LonoraError, match="context_limit_exceeded"):
        prepare_context(request, [], descriptor(5000), policy)
    unknown = prepare_context(request, [], None, policy)
    assert unknown.diagnostics["context_window"] is None
    assert unknown.diagnostics["capacity_source"] == "unknown"
    assert unknown.diagnostics["estimated"]
    assert unknown.diagnostics["estimated_input_tokens"] > 8192
    schema = ToolDefinition(
        name="large", description="Large tool", parameters={"description": "schema-value " * 4000}
    )
    with pytest.raises(LonoraError, match="context_limit_exceeded"):
        prepare_context(
            [ModelMessage(role="user", content="Hi")], [schema], descriptor(5000), policy
        )
    plain = prepare_context([ModelMessage(role="user", content="Hi")], [], descriptor(5000), policy)
    small = ToolDefinition(name="read", description="Read", parameters={"type": "object"})
    with_tool = prepare_context(
        [ModelMessage(role="user", content="Hi")], [small], descriptor(5000), policy
    )
    assert (
        with_tool.diagnostics["estimated_input_tokens"]
        > plain.diagnostics["estimated_input_tokens"]
    )


def test_invalid_exchange_and_unrepresentable_latest_call_fail_closed() -> None:
    with pytest.raises(LonoraError, match="invalid_tool_exchange"):
        govern_context([ModelMessage(role="tool", tool_call_id="orphan", content="OK")])
    messages = exchange()
    messages[0].tool_calls[0].arguments = {"huge": " ".join(f"arg-{i}" for i in range(4000))}
    with pytest.raises(LonoraError, match="context_limit_exceeded"):
        prepare_context(messages, [], descriptor(5000), ModelContextPolicy())


def test_utf8_and_policy_validation_do_not_invent_provider_usage() -> None:
    assert token_estimate(ModelMessage(role="user", content="ذهب")) > token_estimate(
        ModelMessage(role="user", content="abc")
    )
    for field in ("context_window", "maximum_output_tokens"):
        with pytest.raises(ValidationError):
            ModelDescriptor.model_validate({**descriptor(5000).model_dump(), field: -1})
    with pytest.raises(ValidationError):
        ModelContextPolicy(image_tokens=0)
    model = descriptor(5000).model_copy(update={"maximum_output_tokens": 200})
    result = prepare_context(
        [ModelMessage(role="user", content="Inspect")], [], model, ModelContextPolicy()
    )
    assert result.output_tokens == 200


@pytest_asyncio.fixture
async def router_db() -> AsyncGenerator[Database]:
    db = Database.connect("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield db
    await db.close()


class FixtureCredentials(ProviderCredentials):
    def __init__(self) -> None:
        pass

    async def resolve(self, provider: str) -> str:
        return "fixture-not-a-real-key"


async def settings(db: Database, values: dict[str, Any]) -> None:
    async with db.sessions() as session, session.begin():
        for key, value in values.items():
            await SettingsRepository().put(session, key, value)


@pytest.mark.asyncio
async def test_actual_router_rebuilds_context_for_smaller_fallback(router_db: Database) -> None:
    primary = ModelSelection(provider="openai", model="large")
    backup = ModelSelection(provider="openai", model="small")
    await settings(
        router_db,
        {
            "model_routing": RoutingPolicy(unified=primary).model_dump(mode="json"),
            "model_backups": {"choices": [backup.model_dump(mode="json")]},
            "catalog:openai": {
                "models": [
                    descriptor(w).model_copy(update={"id": m}).model_dump()
                    for m, w in [("large", 40000), ("small", 6000)]
                ]
            },
        },
    )
    payloads: list[dict[str, Any]] = []
    clients: list[httpx.AsyncClient] = []
    attempts: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if payload["model"] == "large":
            return httpx.Response(429, json={"error": "scripted rate limit"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Verified fixture result"}}],
                "usage": {"prompt_tokens": 77, "completion_tokens": 12},
            },
        )

    def factory(_: str, key: str) -> ModelAdapter:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        clients.append(client)
        adapter = OpenAIAdapter(key, client)
        adapter.owns_client = True
        return adapter

    async def attempt(selection: ModelSelection) -> None:
        attempts.append(selection.model)

    messages = [
        ModelMessage(role="system", content="Follow server authority."),
        ModelMessage(role="user", content="Earlier request"),
        ModelMessage(role="assistant", content="historical analysis " * 3000),
        ModelMessage(role="user", content="Current request: read market state only"),
        *exchange('{"ok":true,"operation_id":"op-42"}'),
    ]
    original = [m.model_dump() for m in messages]
    reply, selected = await GlobalModelRouter(router_db, FixtureCredentials(), factory).complete(
        Capability.CONVERSATION, messages, [], on_attempt=attempt
    )
    assert selected == backup and attempts == ["large", "small"]
    assert len(payloads[0]["messages"]) > len(payloads[1]["messages"])
    assert payloads[1]["messages"][1]["content"] == "Current request: read market state only"
    assert payloads[1]["messages"][-1]["tool_call_id"] == "financial-receipt"
    assert payloads[0]["max_completion_tokens"] == 4096
    assert payloads[1]["max_completion_tokens"] == 1500
    budget = reply.provider_metadata["context_budget"]
    assert budget["context_window"] == 6000
    assert budget["actual_input_tokens"] == 77 and budget["actual_output_tokens"] == 12
    assert budget["estimated_input_tokens"] <= 6000 - 1500 - 1024
    assert all(client.is_closed for client in clients)
    assert [m.model_dump() for m in messages] == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "adapter_type",
    [OpenAIAdapter, AnthropicAdapter, DeepSeekAdapter, ZaiAdapter, OpenRouterAdapter],
)
async def test_provider_wire_output_budget(adapter_type: type[Any], stream: bool) -> None:
    payloads: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        if stream:
            events = (
                [
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": "OK"},
                    },
                    {"type": "message_stop"},
                ]
                if adapter_type is AnthropicAdapter
                else [{"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]}]
            )
            return httpx.Response(
                200, text="".join("data: " + json.dumps(x) + "\n\n" for x in events)
            )
        if adapter_type is AnthropicAdapter:
            return httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        adapter = adapter_type("fixture-key", client)
        chunks: list[str] = []

        async def delta(text: str) -> None:
            chunks.append(text)

        await adapter.complete(
            "fixture-model",
            [ModelMessage(role="user", content="Read")],
            [],
            max_output_tokens=321,
            on_delta=delta if stream else None,
        )
        if stream:
            assert chunks == ["OK"]
    field = "max_completion_tokens" if adapter_type is OpenAIAdapter else "max_tokens"
    assert payloads[0][field] == 321


@pytest.mark.parametrize("cache_state", ["missing", "corrupt", "disabled"])
def test_missing_or_corrupt_tokenizer_cache_is_offline_and_explicit(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, cache_state: str
) -> None:
    from lonora_adapter_kit.tokenization import cached_encoding, text_counter

    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", "" if cache_state == "disabled" else str(tmp_path))
    if cache_state == "corrupt":
        url = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
        key = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()
        (tmp_path / key).write_bytes(b"corrupt fixture, not encoding data")

    def no_download(_: str) -> None:
        pytest.fail("Request path attempted tokenizer loading without verified cache")

    monkeypatch.setattr("tiktoken.get_encoding", no_download)
    cached_encoding.cache_clear()
    try:
        name, count = text_counter("openai", "gpt-4o")
        assert name == "utf8_bytes_fallback_v1"
        assert count("ذهب") == len("ذهب".encode())
    finally:
        cached_encoding.cache_clear()


def test_real_tool_catalog_fits_default_admission_with_tokenizer() -> None:
    from lonora_adapter_kit.tokenization import text_counter
    from lonora_tools.loader import load_tools

    name, _ = text_counter("openai", "gpt-4o")
    assert name != "utf8_bytes_fallback_v1", "Run scripts/cache_model_tokenizers.py during setup"
    prepared = prepare_context(
        [
            ModelMessage(
                role="system", content="Server controls remain authoritative. " + "{}[]:," * 4000
            ),
            ModelMessage(role="user", content="حلل السوق من بيانات الوسيط دون تنفيذ صفقة"),
        ],
        load_tools().definitions(),
        None,
        ModelContextPolicy(),
        provider="openai",
        model="gpt-4o",
    )
    assert 32000 < prepared.diagnostics["estimated_input_tokens"] <= 64000
