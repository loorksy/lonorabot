"""Model-request-only raster hydration never mutates checkpoint messages."""

import asyncio
import base64
import json
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_adapters.models.anthropic import AnthropicAdapter
from lonora_adapters.models.deepseek import DeepSeekAdapter
from lonora_adapters.models.openai import OpenAIAdapter
from lonora_adapters.models.openrouter import OpenRouterAdapter
from lonora_adapters.models.zai import ZaiAdapter
from lonora_agent.context.image_observations import (
    prepare_image_observations,
    requested_observations,
)
from lonora_core.user_error import LonoraError
from lonora_tools.context import ToolContext


def exchange(count: int = 1) -> list[ModelMessage]:
    calls = [
        ToolCall(
            id=str(i), name="artifact_read", arguments={"artifact_id": str(i), "view_image": True}
        )
        for i in range(count)
    ]
    return [ModelMessage(role="assistant", content="", tool_calls=calls)] + [
        ModelMessage(
            role="tool",
            tool_call_id=call.id,
            content=json.dumps(
                {
                    "ok": True,
                    "image_observation": {
                        "artifact_id": call.id,
                        "sha256": "a" * 64,
                        "media_type": "image/png",
                    },
                }
            ),
        )
        for call in calls
    ]


def test_observation_matches_explicit_tool_request_and_complete_block():
    rows = exchange()
    assert len(requested_observations(rows)) == 1
    rows[0].tool_calls[0].arguments["view_image"] = False
    assert not requested_observations(rows)
    rows = exchange()
    rows[1].content = rows[1].content.replace('"ok": true', '"ok": false')
    assert not requested_observations(rows)
    with pytest.raises(LonoraError, match="invalid_tool_exchange"):
        requested_observations(exchange(2)[:-1])


def test_hydration_is_bounded_and_after_complete_block_and_revalidated():
    async def check() -> None:
        rows = exchange(6)
        original = [m.model_dump() for m in rows]

        async def load(
            context: ToolContext, identity: str, digest: str
        ) -> tuple[dict[str, Any], bytes]:
            return {"artifact_id": identity, "media_type": "image/png", "sha256": digest}, b"pixels"

        loader = AsyncMock(side_effect=load)
        with patch("lonora_agent.context.image_observations.load_image_observation", loader):
            prepared, diagnostics = await prepare_image_observations(
                cast(ToolContext, object()), rows
            )
            assert diagnostics == {
                "available": 4,
                "unavailable": 0,
                "bytes": 24,
                "total_candidates": 6,
                "omitted": 2,
            }
            assert [m.role for m in prepared] == ["assistant"] + ["tool"] * 6 + ["user"] * 5
            assert [m.model_dump() for m in rows] == original
            assert all(not m.images for m in rows)
            await prepare_image_observations(cast(ToolContext, object()), rows)
            assert loader.await_count == 8
            assert [item.args[1] for item in loader.await_args_list[:4]] == ["2", "3", "4", "5"]
            notice = json.loads(
                prepared[-1]
                .content.split("<image_observation_limit>")[1]
                .split("</image_observation_limit>")[0]
            )
            assert [ref["artifact_id"] for ref in notice["source_refs"]] == ["0", "1"]
            assert notice["omitted"] == 2 and not notice["source_refs_truncated"]
        with patch(
            "lonora_agent.context.image_observations.load_image_observation",
            side_effect=LonoraError("artifact_integrity_failed", 409),
        ):
            prepared, diagnostics = await prepare_image_observations(
                cast(ToolContext, object()), rows
            )
            assert diagnostics["unavailable"] == 4 and diagnostics["available"] == 0
            assert not any(m.images for m in prepared)
            assert '"code": "artifact_integrity_failed"' in prepared[-2].content
            assert '"omitted": 2' in prepared[-1].content

    asyncio.run(check())


@pytest.mark.parametrize(
    "adapter_type",
    [OpenAIAdapter, AnthropicAdapter, DeepSeekAdapter, ZaiAdapter, OpenRouterAdapter],
)
def test_all_provider_http_payloads_contain_pixels_after_tool_results(
    adapter_type: type[OpenAIAdapter]
    | type[AnthropicAdapter]
    | type[DeepSeekAdapter]
    | type[ZaiAdapter]
    | type[OpenRouterAdapter],
) -> None:
    async def check() -> None:
        png = b"real-local-raster-bytes"
        seen: list[dict[str, Any]] = []

        def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            seen.append(payload)
            if adapter_type is AnthropicAdapter:
                blocks = payload["messages"][-1]["content"]
                assert [b["type"] for b in blocks] == [
                    "tool_result",
                    "tool_result",
                    "text",
                    "image",
                    "text",
                    "image",
                ]
                assert base64.b64decode(blocks[-1]["source"]["data"]) == png
                return httpx.Response(200, json={"content": [{"type": "text", "text": "seen"}]})
            wire = payload["messages"]
            assert [m["role"] for m in wire] == ["assistant", "tool", "tool", "user", "user"]
            assert (
                base64.b64decode(wire[-1]["content"][-1]["image_url"]["url"].split(",")[1]) == png
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": "seen"}}]})

        async def load(
            context: ToolContext, identity: str, digest: str
        ) -> tuple[dict[str, Any], bytes]:
            return {"artifact_id": identity, "media_type": "image/png", "sha256": digest}, png

        with patch(
            "lonora_agent.context.image_observations.load_image_observation", side_effect=load
        ):
            messages, _ = await prepare_image_observations(cast(ToolContext, object()), exchange(2))
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            reply = await adapter_type("test-only", client).complete("test-vision", messages, [])
            assert reply.text == "seen" and len(seen) == 1

    asyncio.run(check())


def test_original_user_images_unchanged_and_stale_worker_cannot_hydrate() -> None:
    async def check() -> None:
        original = ModelMessage(
            role="user", content="Uploaded evidence", images=["data:image/png;base64,b3JpZ2luYWw="]
        )
        rows = [original, *exchange()]
        with patch(
            "lonora_agent.context.image_observations.load_image_observation",
            side_effect=LonoraError("artifact_file_missing", 404),
        ):
            prepared, stats = await prepare_image_observations(cast(ToolContext, object()), rows)
            assert prepared[0] == original and stats["unavailable"] == 1
        with patch(
            "lonora_agent.context.image_observations.load_image_observation",
            side_effect=LonoraError("stale_lease", 409),
        ):
            with pytest.raises(LonoraError, match="stale_lease"):
                await prepare_image_observations(cast(ToolContext, object()), rows)

    asyncio.run(check())


def test_duplicate_source_is_one_observation_not_failure_or_omission() -> None:
    async def check() -> None:
        rows = exchange(2)
        rows[0].tool_calls[1].arguments["artifact_id"] = "0"
        rows[2].content = rows[2].content.replace('"artifact_id": "1"', '"artifact_id": "0"')
        loader = AsyncMock(
            return_value=(
                {"artifact_id": "0", "media_type": "image/png", "sha256": "a" * 64},
                b"pixels",
            )
        )
        with patch("lonora_agent.context.image_observations.load_image_observation", loader):
            prepared, diagnostics = await prepare_image_observations(
                cast(ToolContext, object()), rows
            )
        assert diagnostics == {
            "available": 1,
            "unavailable": 0,
            "bytes": 6,
            "total_candidates": 1,
            "omitted": 0,
        }
        assert loader.await_count == 1
        assert len(prepared) == 4 and prepared[-1].images
        assert not any("<image_observation_limit>" in row.content for row in prepared)

    asyncio.run(check())


def test_omission_notice_source_list_is_bounded() -> None:
    async def check() -> None:
        loader = AsyncMock(
            return_value=(
                {"artifact_id": "selected", "media_type": "image/png", "sha256": "a" * 64},
                b"pixels",
            )
        )
        with patch("lonora_agent.context.image_observations.load_image_observation", loader):
            prepared, diagnostics = await prepare_image_observations(
                cast(ToolContext, object()), exchange(25)
            )
        assert loader.await_count == 4 and diagnostics["omitted"] == 21
        notice = json.loads(
            prepared[-1]
            .content.split("<image_observation_limit>")[1]
            .split("</image_observation_limit>")[0]
        )
        assert len(notice["source_refs"]) == 4 and notice["source_refs_truncated"]
        assert not prepared[-1].images

    asyncio.run(check())


def test_actual_router_fallback_preserves_owner_and_image_exchange_or_rejects() -> None:
    from lonora_adapter_kit.model import ModelAdapter
    from lonora_contracts.model_catalog import ModelDescriptor
    from lonora_contracts.model_routing import Capability, ModelSelection, RoutingPolicy
    from lonora_db.client import Database
    from lonora_db.schema import Base
    from lonora_db.transactions import SettingsRepository
    from lonora_providers.credentials import ProviderCredentials
    from lonora_providers.router import GlobalModelRouter

    class Credentials(ProviderCredentials):
        def __init__(self) -> None:
            pass

        async def resolve(self, provider: str) -> str:
            return "scripted-only-key"

    async def check() -> None:
        db = Database.connect("sqlite+aiosqlite:///:memory:")
        clients: list[httpx.AsyncClient] = []
        payloads: list[dict[str, Any]] = []
        try:
            async with db.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with db.sessions() as session, session.begin():
                for key, value in {
                    "model_routing": RoutingPolicy(
                        unified=ModelSelection(provider="openai", model="large")
                    ).model_dump(mode="json"),
                    "model_backups": {"choices": [{"provider": "openai", "model": "small"}]},
                    "catalog:openai": {
                        "models": [
                            ModelDescriptor(
                                id=name,
                                provider="openai",
                                name=name,
                                context_window=window,
                                source="scripted:catalog",
                            ).model_dump()
                            for name, window in [("large", 60000), ("small", 16000)]
                        ]
                    },
                }.items():
                    await SettingsRepository().put(session, key, value)

            def response(request: httpx.Request) -> httpx.Response:
                payload = json.loads(request.content)
                payloads.append(payload)
                if payload["model"] == "large":
                    return httpx.Response(429, json={"error": "scripted fallback"})
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "Inspected current pixels only"}}]},
                )

            def factory(provider: str, key: str) -> ModelAdapter:
                client = httpx.AsyncClient(transport=httpx.MockTransport(response))
                clients.append(client)
                return OpenAIAdapter(key, client)

            old = exchange()
            current = exchange()
            current[0].tool_calls[0].id = "current"
            current[0].tool_calls[0].arguments["artifact_id"] = "current"
            current[1].tool_call_id = "current"
            current[1].content = current[1].content.replace(
                '"artifact_id": "0"', '"artifact_id": "current"'
            )
            owner = "Current owner instruction: inspect only, never trade."
            rows = [
                ModelMessage(role="user", content="Old request"),
                *old,
                ModelMessage(role="user", content=owner),
                *current,
            ]

            async def load(
                context: ToolContext, identity: str, digest: str
            ) -> tuple[dict[str, Any], bytes]:
                return {
                    "artifact_id": identity,
                    "media_type": "image/png",
                    "sha256": digest,
                }, identity.encode()

            with patch(
                "lonora_agent.context.image_observations.load_image_observation", side_effect=load
            ):
                prepared, _ = await prepare_image_observations(cast(ToolContext, object()), rows)
            assert all(m.context_origin == "tool_observation" for m in prepared if m.images)
            reply, selection = await GlobalModelRouter(db, Credentials(), factory).complete(
                Capability.VISION, prepared, []
            )
            assert selection.model == "small" and reply.text
            assert len(payloads) == 2
            wire = payloads[-1]["messages"]
            assert any(m.get("content") == owner for m in wire)
            assert [m["tool_call_id"] for m in wire if m["role"] == "tool"] == ["current"]
            image_messages = [m for m in wire if isinstance(m.get("content"), list)]
            assert len(image_messages) == 1
            assert (
                base64.b64decode(image_messages[0]["content"][-1]["image_url"]["url"].split(",")[1])
                == b"current"
            )
            assert all(
                "context_origin" not in m for payload in payloads for m in payload["messages"]
            )
            # With a window below the current image cost, admission must reject;
            # dropping the owner or latest exchange to keep orphan pixels is forbidden.
            from lonora_contracts.model_context import ModelContextPolicy
            from lonora_providers.context import prepare_context

            with pytest.raises(LonoraError, match="context_limit_exceeded"):
                prepare_context(
                    prepared,
                    [],
                    ModelDescriptor(
                        id="tiny",
                        provider="openai",
                        name="Tiny",
                        context_window=6000,
                        source="scripted:catalog",
                    ),
                    ModelContextPolicy(),
                )
        finally:
            for client in clients:
                await client.aclose()
            await db.close()

    asyncio.run(check())


def test_omission_notice_stays_with_exchange_before_later_owner_steering() -> None:
    from lonora_adapter_kit.context import context_blocks

    async def check() -> None:
        rows = [*exchange(6), ModelMessage(role="user", content="Newest owner steering")]
        loader = AsyncMock(return_value=({"media_type": "image/png"}, b"pixels"))
        with patch("lonora_agent.context.image_observations.load_image_observation", loader):
            prepared, _ = await prepare_image_observations(cast(ToolContext, object()), rows)
        blocks = context_blocks(prepared)
        assert len(blocks) == 2 and blocks[-1][0].content == "Newest owner steering"
        assert "<image_observation_limit>" in blocks[0][-1].content
        assert all(row.context_origin == "tool_observation" for row in blocks[0][7:])
        assert blocks[-1][0].context_origin == "conversation"

    asyncio.run(check())
