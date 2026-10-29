"""Explicit PostgreSQL + built renderer + Chromium acceptance; simulation only."""

import asyncio
import base64
import json
import shutil
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import uvicorn
from check_streaming import Fixture
from fastapi import FastAPI
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.context.image_observations import prepare_image_observations
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_api.chart_renderer import install_chart_renderer
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.schema import RunRow
from lonora_db.transactions import resource_data
from lonora_security.runtime_storage import confined_path
from lonora_tools import chart_snapshot as snapshot_module
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from PIL import Image


@contextmanager
def renderer_server() -> Generator[str]:
    root = Path(__file__).resolve().parents[1] / "apps/web/dist"
    if not (root / "chart-runtime/index.html").is_file():
        raise SystemExit("Build apps/web dedicated chart renderer first")
    app = FastAPI()
    install_chart_renderer(app, root)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{sock.getsockname()[1]}/charts/render"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


async def main(url: str) -> None:
    fixture = await Fixture().open()
    executable = shutil.which("chromium")
    if not executable:
        raise SystemExit("Install Chromium before this explicit browser acceptance check")
    visual = ChartVisualRuntime(url, executable, chromium_sandbox=False)
    connection_id: str | None = None
    with TemporaryDirectory() as directory:
        try:
            agent = await fixture.agent("Browser visual observation")
            thread = await fixture.conversation(agent)
            context = replace(
                await fixture.lease(await fixture.run(agent, thread)),
                artifact_root=Path(directory),
                chart_visual=visual,
            )
            registry = load_tools()

            async def call(
                name: str,
                args: dict[str, Any],
                identity: str | None = None,
                actor: ToolContext = context,
            ) -> dict[str, Any]:
                return await registry.execute(
                    ToolCall(id=identity or uuid4().hex, name=name, arguments=args), actor
                )

            async def fails(
                args: dict[str, Any], identity: str, code: str, actor: ToolContext = context
            ) -> None:
                try:
                    await call("chart_snapshot", args, identity, actor)
                except LonoraError as error:
                    assert error.code == code, (error.code, code)
                else:
                    raise AssertionError("Expected " + code)

            markets = [
                ("EURUSDm", "15m"),
                ("XAUUSDm", "1h"),
                ("US500.cash", "4h"),
                ("BTCUSD#", "5m"),
            ]
            start = datetime(2026, 10, 19, tzinfo=UTC)
            bars = {
                symbol + ":" + timeframe: [
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "time": (start + timedelta(minutes=15 * i)).isoformat(),
                        "open": str(100 + i / 10),
                        "high": str(103 + i / 10),
                        "low": str(98 + i / 10),
                        "close": str(101 + i / 10),
                    }
                    for i in range(80)
                ]
                for symbol, timeframe in markets
            }
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": "visual-" + uuid4().hex,
                    "enabled": True,
                },
            )
            connection_id = str(connection["id"])
            await fixture.request(
                "POST",
                f"/trading/connections/{connection_id}/simulation",
                {
                    "snapshot": {"balance": "10000", "currency": "USD", "candles": bars},
                },
            )
            await fails(
                {
                    "renderer": "tradingview",
                    "account_id": connection_id,
                    "symbol": "EURUSDm",
                    "timeframe": "15m",
                },
                "browser-without-chart",
                "tool_arguments_invalid",
            )
            originals: list[dict[str, Any]] = []
            with patch.object(visual, "capture", wraps=visual.capture) as capture:
                for index, (symbol, timeframe) in enumerate(markets):
                    chart = await call(
                        "chart_open",
                        {
                            "account_id": connection_id,
                            "symbol": symbol,
                            "timeframe": timeframe,
                        },
                    )
                    chart_id = chart["chart"]["id"]
                    args = {
                        "chart_id": chart_id,
                        "renderer": "tradingview",
                        "locale": "ar" if index % 2 else "en",
                    }
                    snapshot = await call("chart_snapshot", args, f"capture-{index}")
                    originals.append(snapshot)
                    descriptor = snapshot["chart_snapshot"]
                    receipt = descriptor["renderer_receipt"]
                    assert descriptor["source"] == "tradingview_renderer"
                    assert receipt["applied"] is True and receipt["locale"] == args["locale"]
                    assert receipt["symbol"] == symbol and receipt["timeframe"] == timeframe
                    assert (
                        receipt["chart_id"] == chart_id and receipt["account_id"] == connection_id
                    )
                    assert receipt["data_revision"] == descriptor["data_revision"]
                    path = confined_path(context.artifact_root, snapshot["payload"]["key"])
                    content = path.read_bytes()
                    with Image.open(BytesIO(content)) as png:
                        assert png.format == "PNG" and png.size == (
                            receipt["width"],
                            receipt["height"],
                        )
                    await call(
                        "chart_annotate",
                        {
                            "chart_id": chart_id,
                            "version": 1,
                            "annotation": {"type": "price", "price": 110, "label": "Later change"},
                        },
                    )
                    replay = await call("chart_snapshot", args, f"capture-{index}")
                    assert replay["chart_snapshot"] == descriptor and path.read_bytes() == content
                    assert capture.call_count == index + 1
                    await fails(
                        {**args, "locale": "en" if args["locale"] == "ar" else "ar"},
                        f"capture-{index}",
                        "artifact_nonce_conflict",
                    )
                    await fails(
                        {"chart_id": chart_id}, f"capture-{index}", "artifact_nonce_conflict"
                    )
                    await fails(
                        args,
                        "unconfigured",
                        "chart_visual_unconfigured",
                        replace(context, chart_visual=None),
                    )
                    await fails({**args, "format": "svg"}, "bad-svg", "tool_arguments_invalid")
            # Actual PNG pixels, not just the receipt, enter the same Agent/thread model context.
            snapshot = originals[0]
            read_call = ToolCall(
                id="view-real-capture",
                name="artifact_read",
                arguments={
                    "artifact_id": snapshot["id"],
                    "view_image": True,
                },
            )
            read_result = await registry.execute(read_call, context)
            messages = [
                ModelMessage(role="assistant", content="", tool_calls=[read_call]),
                ModelMessage(
                    role="tool",
                    tool_call_id=read_call.id,
                    content=json.dumps({"ok": True, **read_result}),
                ),
            ]
            prepared, stats = await prepare_image_observations(context, messages)
            assert stats["available"] == 1 and stats["unavailable"] == 0
            pixels = [image for message in prepared for image in message.images]
            assert len(pixels) == 1
            assert (
                base64.b64decode(pixels[0].split(",", 1)[1])
                == confined_path(context.artifact_root, snapshot["payload"]["key"]).read_bytes()
            )
            # Recovered pending native snapshot -> receipt replay -> image inspection ->
            # capability router receives real pixels, with no second browser capture.
            pending = ToolCall(
                id="capture-0",
                name="chart_snapshot",
                arguments={
                    "chart_id": snapshot["chart_id"],
                    "renderer": "tradingview",
                    "locale": "en",
                },
            )
            await persist(
                context,
                {"environment": {"version": 1}},
                [
                    ModelMessage(role="user", content="Inspect the saved chart before explaining"),
                    ModelMessage(role="assistant", content="", tool_calls=[pending]),
                ],
                [pending],
            )

            class Router:
                stage = 0

                async def complete(
                    self,
                    capability: Capability,
                    messages: list[ModelMessage],
                    tools: list[ToolDefinition],
                    **kwargs: Any,
                ) -> tuple[ModelReply, ModelSelection]:
                    self.stage += 1
                    selection = ModelSelection(provider="openai", model="scripted-browser-vision")
                    if self.stage == 1:
                        observation = next(
                            message for message in reversed(messages) if message.role == "tool"
                        )
                        result = json.loads(observation.content)
                        assert result["id"] == snapshot["id"]
                        assert result["chart_snapshot"]["source"] == "tradingview_renderer"
                        return ModelReply(tool_calls=[read_call]), selection
                    observation = next(
                        message
                        for message in reversed(messages)
                        if message.images and message.context_origin == "tool_observation"
                    )
                    assert capability is Capability.VISION
                    assert (
                        base64.b64decode(observation.images[0].split(",", 1)[1])
                        == confined_path(
                            context.artifact_root, snapshot["payload"]["key"]
                        ).read_bytes()
                    )
                    return ModelReply(text="Inspected actual saved renderer pixels."), selection

            router = Router()
            with patch.object(visual, "capture", wraps=visual.capture) as replay_capture:
                outcome = await execute_tool_loop(replace(context, router=router), registry, 8)
                assert outcome.text == "Inspected actual saved renderer pixels."
                assert router.stage == 2 and replay_capture.call_count == 0
            async with context.db.sessions() as session:
                run = await session.get(RunRow, context.lease.run_id)
                assert run is not None and "data:image" not in json.dumps(run.execution_state)
            await fails(
                {"chart_id": snapshot["chart_id"], "renderer": "tradingview"},
                "capture-0",
                "artifacts_not_found",
                replace(context, thread_id="another-thread"),
            )

            class WorkerKilled(BaseException):
                pass

            crash_call = ToolCall(
                id="crash-after-image-write",
                name="chart_snapshot",
                arguments={
                    "chart_id": originals[-1]["chart_id"],
                    "renderer": "tradingview",
                    "locale": "ar",
                },
            )
            await persist(
                context,
                {"environment": {"version": 1}},
                [
                    ModelMessage(role="user", content="Inspect the exact saved browser snapshot"),
                    ModelMessage(role="assistant", content="", tool_calls=[crash_call]),
                ],
                [crash_call],
            )
            real_store = snapshot_module.store_artifact

            async def store_then_kill(*args: Any, **kwargs: Any) -> dict[str, Any]:
                await real_store(*args, **kwargs)
                raise WorkerKilled()

            with patch.object(visual, "capture", wraps=visual.capture) as crash_capture:
                with patch.object(snapshot_module, "store_artifact", new=store_then_kill):
                    try:
                        await execute_tool_loop(context, registry, 8)
                    except WorkerKilled:
                        pass
                    else:
                        raise AssertionError("Expected worker death after durable artifact receipt")
                assert crash_capture.call_count == 1
                async with context.db.sessions() as session:
                    run = await session.get(RunRow, context.lease.run_id)
                    assert run is not None
                    assert (
                        run.execution_state["environment"]["inflight"]["call_id"] == crash_call.id
                    )
                    artifact = await ArtifactRepository().get(
                        session, context.owner_id, context.for_call(crash_call.id).resource_id
                    )
                    snapshot = resource_data(artifact)
                    snapshot["chart_id"] = artifact.state["chart_snapshot"]["chart_id"]
                    original_receipt = artifact.state["chart_snapshot"]
                    original_content = confined_path(
                        context.artifact_root, artifact.payload["key"]
                    ).read_bytes()
                recovered = replace(
                    await fixture.lease(
                        {
                            "id": context.lease.run_id,
                            "agent_id": context.agent_id,
                            "thread_id": context.thread_id,
                        }
                    ),
                    artifact_root=context.artifact_root,
                    chart_visual=visual,
                )
                await fails(crash_call.arguments, crash_call.id, "stale_lease", context)
                read_call = ToolCall(
                    id="inspect-after-kill",
                    name="artifact_read",
                    arguments={
                        "artifact_id": snapshot["id"],
                        "view_image": True,
                    },
                )
                recovered_router = Router()
                result = await execute_tool_loop(
                    replace(recovered, router=recovered_router), registry, 8
                )
                assert result.text == "Inspected actual saved renderer pixels."
                assert crash_capture.call_count == 1 and recovered_router.stage == 2
                async with recovered.db.sessions() as session:
                    artifact = await ArtifactRepository().get(
                        session, recovered.owner_id, snapshot["id"]
                    )
                    assert artifact.state["chart_snapshot"] == original_receipt
                    assert (
                        confined_path(recovered.artifact_root, artifact.payload["key"]).read_bytes()
                        == original_content
                    )
                    run = await session.get(RunRow, recovered.lease.run_id)
                    assert run is not None
                    assert "tool_execution_uncertain" not in json.dumps(run.execution_state)
            print(
                "PASS real TradingView PNGs, exact four-market/four-timeframe AR/EN receipts, immutable replay, locale/format/scope/config guards, same-Agent model image pixels"
            )
        finally:
            await visual.close()
            if connection_id:
                await fixture.request("DELETE", "/trading/connections/" + connection_id)
            await fixture.close()


if __name__ == "__main__":
    with renderer_server() as renderer_url:
        asyncio.run(main(renderer_url))
