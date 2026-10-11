import json

import httpx
import pytest
from pydantic import SecretStr

from lonora.config import Settings
from lonora.provider import GlobalModelRouter


def router_with_key(transport: httpx.AsyncBaseTransport) -> GlobalModelRouter:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret=SecretStr("test-signing-key-that-is-long-enough-123"),
        model_api_key=SecretStr("provider-test-key"),
    )
    return GlobalModelRouter(settings, transport=transport)


@pytest.mark.asyncio
async def test_openai_compatible_provider_and_model_discovery():
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer provider-test-key"
        if request.url.path.endswith("/chat/completions"):
            payload = json.loads(request.content)
            assert payload["model"] == "selected-model"
            assert payload["messages"][-1]["content"] == "Hello"
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Hello back"}}]},
            )
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})

    router = router_with_key(httpx.MockTransport(handle))
    answer = await router.respond(
        [{"role": "system", "content": "Be concise"}, {"role": "user", "content": "Hello"}],
        provider="openai",
        model_name="selected-model",
    )
    models = await router.discover_models("openai")
    assert answer == "Hello back"
    assert models == [{"id": "model-a", "name": "model-a"}, {"id": "model-b", "name": "model-b"}]


@pytest.mark.asyncio
async def test_anthropic_uses_native_messages_protocol():
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "provider-test-key"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert payload["system"] == "Be concise"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " there"},
                ]
            },
        )

    router = router_with_key(httpx.MockTransport(handle))
    answer = await router.respond(
        [{"role": "system", "content": "Be concise"}, {"role": "user", "content": "Hello"}],
        provider="anthropic",
        model_name="claude-model",
    )
    assert answer == "Hello there"
