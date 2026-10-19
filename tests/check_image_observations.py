"""Real PostgreSQL tool-loop restart and same-Agent runtime image inspection; simulation only."""

import asyncio
import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.context.image_observations import prepare_image_observations
from lonora_agent.runtime import AgentRuntime
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import RunRow
from lonora_security.runtime_storage import confined_path
from lonora_tools.artifacts import load_image_observation, read, store_artifact
from lonora_tools.loader import load_tools
from PIL import Image


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    with TemporaryDirectory() as directory:
        try:
            agent = await fixture.agent("Image observation runtime")
            thread = await fixture.conversation(agent)
            context = replace(
                await fixture.lease(await fixture.run(agent, thread)), artifact_root=Path(directory)
            )
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "image-demo", "enabled": True},
            )
            connection_id = connection["id"]
            candles = [
                {
                    "symbol": "EURUSDm",
                    "timeframe": "1h",
                    "time": (datetime(2026, 10, 1, tzinfo=UTC) + timedelta(hours=i)).isoformat(),
                    "open": "1.10",
                    "high": "1.12",
                    "low": "1.09",
                    "close": "1.11",
                }
                for i in range(8)
            ]
            await fixture.request(
                "POST",
                f"/trading/connections/{connection_id}/simulation",
                {
                    "snapshot": {
                        "balance": "10000",
                        "currency": "USD",
                        "candles": {"EURUSDm:1h": candles},
                    }
                },
            )
            registry = load_tools()
            snap = ToolCall(
                id="snapshot",
                name="chart_snapshot",
                arguments={"account_id": connection_id, "symbol": "EURUSDm", "timeframe": "1h"},
            )
            await persist(
                context,
                {"environment": {"version": 1}},
                [
                    ModelMessage(role="user", content="Inspect the chart before explaining"),
                    ModelMessage(role="assistant", content="", tool_calls=[snap]),
                ],
                [snap],
            )
            observed_id = ""

            class Interrupted(Exception):
                pass

            class Router:
                stage = 0

                async def complete(
                    self,
                    capability: Capability,
                    messages: list[ModelMessage],
                    tools: list[ToolDefinition],
                    **kwargs: Any,
                ) -> tuple[ModelReply, ModelSelection]:
                    nonlocal observed_id
                    self.stage += 1
                    selection = ModelSelection(provider="openai", model="scripted-vision")
                    if self.stage == 1:
                        result = json.loads(messages[-1].content)
                        assert result["ok"] and result["payload"]["media_type"] == "image/png"
                        observed_id = result["id"]
                        return ModelReply(
                            tool_calls=[
                                ToolCall(
                                    id="inspect",
                                    name="artifact_read",
                                    arguments={"artifact_id": observed_id, "view_image": True},
                                ),
                                ToolCall(
                                    id="metadata",
                                    name="artifact_read",
                                    arguments={"artifact_id": observed_id},
                                ),
                            ]
                        ), selection
                    assert capability is Capability.VISION
                    assert messages[-1].role == "user" and messages[-1].images
                    assert (
                        messages[-2].tool_call_id == "metadata"
                        and messages[-3].tool_call_id == "inspect"
                    )
                    with Image.open(
                        BytesIO(base64.b64decode(messages[-1].images[0].split(",")[1]))
                    ) as image:
                        assert image.format == "PNG" and image.width > 0
                    assert '"symbol": "EURUSDm"' in messages[-1].content
                    if self.stage == 2:
                        raise Interrupted()
                    return ModelReply(
                        text="Inspected saved chart pixels; not a user-delivery receipt."
                    ), selection

            router = Router()
            context = replace(context, router=router)
            try:
                await execute_tool_loop(context, registry, 8)
            except Interrupted:
                pass
            else:
                raise AssertionError("expected interruption after real image hydration")
            async with context.db.sessions() as session:
                run = await session.get(RunRow, context.lease.run_id)
                assert run is not None
                saved = json.dumps(run.execution_state)
                assert "data:image" not in saved and "image_observation" in saved
                restored = [
                    ModelMessage.model_validate(row) for row in run.execution_state["messages"]
                ]
            assert all(not row.images for row in restored)
            await AgentRuntime(registry).execute(context)
            async with context.db.sessions() as session:
                run = await session.get(RunRow, context.lease.run_id)
                assert (
                    run
                    and run.status == "completed"
                    and run.execution_state["selection"]["capability"] == "vision"
                )
                assert "data:image" not in json.dumps(run.execution_state)
            # Acquire a separate test Run to exercise scope/freshness while holding a valid lease.
            context = replace(
                await fixture.lease(await fixture.run(agent, thread)), artifact_root=Path(directory)
            )
            for invalid in (
                replace(context, agent_id="other-agent"),
                replace(context, thread_id="other-thread"),
                replace(context, owner_id="other-owner"),
            ):
                try:
                    await read(invalid, {"artifact_id": observed_id, "view_image": True})
                except LonoraError as error:
                    assert error.code == "artifacts_not_found"
                else:
                    raise AssertionError("cross-scope image exposed")
            await load_image_observation(context, observed_id)
            async with context.db.sessions() as session:
                from lonora_db.artifacts import ArtifactRepository

                row = await ArtifactRepository().get(session, context.owner_id, observed_id)
                path = confined_path(context.artifact_root, row.payload["key"])
            path.write_bytes(b"corrupt")
            prepared, stats = await prepare_image_observations(context, restored)
            assert stats["unavailable"] == 1 and not any(m.images for m in prepared)
            path.unlink()
            try:
                await load_image_observation(context, observed_id)
            except LonoraError as error:
                assert error.code == "artifact_file_missing"
            else:
                raise AssertionError("missing image accepted")
            # Actual MIME and geometry validation (metadata alone is not sufficient).
            cases = [(b"not an image", "image/png", "artifact_image_invalid")]
            output = BytesIO()
            Image.new("RGB", (2, 2)).save(output, format="JPEG")
            cases.append((output.getvalue(), "image/png", "artifact_image_format_unsupported"))
            output = BytesIO()
            Image.new("RGB", (4097, 1)).save(output, format="PNG")
            cases.append((output.getvalue(), "image/png", "artifact_image_dimensions_exceeded"))
            cases.append((b"x" * (5 * 1024 * 1024 + 1), "image/png", "artifact_image_too_large"))
            for index, (pixels, media, code) in enumerate(cases):
                result = await store_artifact(
                    context.for_call(f"invalid-{index}"), "image.png", pixels, media
                )
                try:
                    await load_image_observation(context, result["id"])
                except LonoraError as error:
                    assert error.code == code, (error.code, code)
                else:
                    raise AssertionError("invalid raster accepted")
            print(
                "PASS real chart_snapshot -> artifact_read -> same Run VISION pixels; complete multi-tool block; reference-only checkpoint/restart; scope, hash, missing/MIME/dimension/size rejection"
            )
        finally:
            if connection_id:
                await fixture.request("DELETE", "/trading/connections/" + connection_id)
            await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
