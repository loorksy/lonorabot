"""Actual executor/PG attachment delivery and authenticated PNG download; scripted model only."""

import asyncio
import json
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import httpx
from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.artifact_repair import repair_completed_images
from lonora_db.runs import complete_run
from lonora_db.schema import ArtifactRow, EventRow, MessageRow, RunRow
from lonora_security.runtime_storage import confined_path
from lonora_tools.artifacts import store_artifact
from lonora_tools.loader import load_tools
from PIL import Image
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    files: list[Path] = []
    try:
        agent = await fixture.agent("Generated chart attachment fixture")
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        registry = load_tools()
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "attachment-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        connection_id = connection["id"]
        assert isinstance(connection_id, str)
        await fixture.request(
            "POST",
            "/trading/connections/" + connection_id + "/simulation",
            {
                "snapshot": {
                    "balance": "1000",
                    "currency": "USD",
                    "candles": {
                        "XAUUSD:1h": [
                            {
                                "symbol": "XAUUSD",
                                "timeframe": "1h",
                                "time": f"2026-10-01T{index:02d}:00:00Z",
                                "open": str(100 + index),
                                "high": str(104 + index),
                                "low": str(99 + index),
                                "close": str(102 + index),
                            }
                            for index in range(20)
                        ]
                    },
                }
            },
        )
        opened = await registry.execute(
            ToolCall(
                id="open-chart",
                name="chart_open",
                arguments={
                    "account_id": connection_id,
                    "symbol": "XAUUSD",
                    "timeframe": "1h",
                    "indicators": [{"name": "rsi", "period": 14}],
                    "annotations": [
                        {"type": "price", "price": 110, "label": "Actual saved support <script>"}
                    ],
                },
            ),
            context,
        )
        picture_call = ToolCall(
            id="picture-call", name="chart_snapshot", arguments={"chart_id": opened["chart"]["id"]}
        )
        # Tool bytes were persisted, but the worker lost its checkpoint before delivery.
        stored = await registry.execute(picture_call, context)
        path = confined_path(context.artifact_root, stored["payload"]["key"])
        files.append(path)
        original = path.read_bytes()
        replay = await registry.execute(picture_call, context)
        assert replay["id"] == stored["id"] and path.read_bytes() == original
        try:
            await store_artifact(
                context.for_call(picture_call.id),
                stored["payload"]["name"],
                b"different bytes",
                "image/png",
            )
        except LonoraError as error:
            assert error.code == "artifact_nonce_conflict"
        else:
            raise AssertionError("Replay unexpectedly changed an existing artifact")
        assert path.read_bytes() == original
        upload = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("owner-upload.png", original, "image/png")},
            data={"thread_id": thread["id"]},
        )
        assert upload.status_code == 201
        uploaded = upload.json()
        files.append(confined_path(context.artifact_root, uploaded["payload"]["key"]))
        print(
            "PASS generated PNG effect replay is stable and conflicting replay never changes original bytes"
        )

        # The attachment receipt and message must roll back together.
        try:
            async with fixture.runtime.db.sessions() as session, session.begin():
                assert await complete_run(session, context.lease, "", {})
                raise RuntimeError("Explicit fixture transaction rollback")
        except RuntimeError:
            pass
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(ArtifactRow, stored["id"])
            assert row is not None and "delivered_message_id" not in row.state
            assert not list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == thread["id"], MessageRow.role == "assistant"
                    )
                )
            )
        print(
            "PASS rolled-back completion leaves neither a phantom assistant message nor an attachment delivery receipt"
        )

        scripted = [
            ModelReply(tool_calls=[picture_call]),
            ModelReply(text="Here is the chart image."),
        ]

        async def model(*args: Any):
            assert scripted
            return scripted.pop(0), ModelSelection(
                provider="openai", model="explicit-attachment-fixture"
            )

        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(context, registry, 90, 8)
        messages = cast(
            list[dict[str, Any]],
            await fixture.request("GET", "/threads/" + thread["id"] + "/messages"),
        )
        assistant = next(message for message in messages if message["role"] == "assistant")
        assert assistant["attachment_ids"] == [stored["id"]]
        assert uploaded["id"] not in assistant["attachment_ids"]
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(ArtifactRow, stored["id"])
            assert row is not None and row.state["delivered_message_id"] == assistant["id"]
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "message.created", EventRow.run_id == run["id"]
                    )
                )
            )
            assert any(event.payload.get("attachment_ids") == [stored["id"]] for event in events)
        print(
            "PASS actual executor commits generated image IDs into assistant message, history and durable message.created event"
        )
        try:
            await store_artifact(
                context.for_call(picture_call.id),
                stored["payload"]["name"],
                b"stale worker data",
                "image/png",
            )
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("Completed worker unexpectedly rewrote an artifact")
        assert path.read_bytes() == original
        print(
            "PASS completed/stale worker cannot overwrite delivered bytes and unrelated owner upload is not reattached"
        )
        response = await fixture.client.get("/api/artifacts/" + stored["id"] + "/file?preview=true")
        assert response.status_code == 200 and response.headers["content-type"] == "image/png"
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n" and response.content == original
        assert response.headers["x-content-type-options"] == "nosniff"
        with Image.open(BytesIO(response.content)) as image:
            image.load()
            assert image.format == "PNG" and image.width == 960 and image.height == 550
            assert (
                "rsi(14)" in image.info["Description"]
                and "Actual saved support <script>" in image.info["Description"]
            )
            assert len(image.getcolors(image.width * image.height) or []) > 5
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
        ) as anonymous:
            denied = await anonymous.get("/api/artifacts/" + stored["id"] + "/file")
            assert denied.status_code == 401
        print(
            "PASS authenticated download is a decoded plotted PNG with saved indicators/annotations; anonymous download is denied"
        )
        # The model may refer to an already delivered image without another tool call.
        resent_run = await fixture.run(agent, thread)
        resent_context = await fixture.lease(resent_run)
        reference = "![chart](sandbox:/mnt/data/" + stored["payload"]["key"] + ")"
        scripted.append(ModelReply(text="The saved chart.\n" + reference))
        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(resent_context, registry, 90, 8)
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, resent_run["id"])
            assert row is not None
            message = await session.get(MessageRow, row.model_metadata["result_message_id"])
            assert message is not None
            assert message.attachment_ids == [stored["id"]]
            assert message.content == row.result == "The saved chart."
            artifact = await session.get(ArtifactRow, stored["id"])
            assert artifact is not None
            assert artifact.state["delivered_message_id"] == assistant["id"]
        # Wrong storage keys, code examples and other threads cannot grant attachment access.
        for content, other_thread in [
            (reference.replace(".png", "-wrong.png"), False),
            ("`" + reference + "`", False),
            (reference, True),
        ]:
            target = (
                await fixture.request(
                    "POST", "/threads", {"agent_id": agent["id"], "title": "Separate scope"}
                )
                if other_thread
                else thread
            )
            denied_context = await fixture.lease(await fixture.run(agent, target))
            async with fixture.runtime.db.sessions() as session, session.begin():
                assert await complete_run(session, denied_context.lease, content, {})
                row = await session.get(RunRow, denied_context.lease.run_id)
                assert row is not None
                message = await session.get(MessageRow, row.model_metadata["result_message_id"])
                assert message is not None and message.attachment_ids == []
                assert message.content == content
        print(
            "PASS re-sent local image becomes a real attachment; original receipt and scope/code boundaries survive"
        )

        # Reproduce a pre-fix completed message. Recorded effects remain intact,
        # but generated attribution and assistant attachment IDs never existed.
        async with fixture.runtime.db.sessions() as session, session.begin():
            legacy_artifact = await session.get(ArtifactRow, stored["id"])
            legacy_message = await session.get(MessageRow, assistant["id"])
            legacy_run = await session.get(RunRow, run["id"])
            assert (
                legacy_artifact is not None
                and legacy_message is not None
                and legacy_run is not None
            )
            legacy_artifact.state = {}
            legacy_message.attachment_ids = []
            state = dict(legacy_run.execution_state)
            state["messages"] = [
                *state["messages"],
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "not-an-owned-effect", "name": "artifact_create", "arguments": {}}
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "not-an-owned-effect",
                    "content": json.dumps({"ok": True, **uploaded}),
                },
            ]
            legacy_run.execution_state = state
        async with fixture.runtime.db.sessions() as session:
            plan = await repair_completed_images(session, fixture.owner, run["id"])
            assert [candidate["artifact_id"] for candidate in plan["candidates"]] == [stored["id"]]
            assert plan["applied"] == []
            legacy_message = await session.get(MessageRow, assistant["id"])
            assert legacy_message is not None and legacy_message.attachment_ids == []

        async def repair_cli(*flags: str) -> dict[str, Any]:
            process = await asyncio.to_thread(
                subprocess.run,
                [
                    ".venv/bin/python",
                    "scripts/repair-generated-artifacts.py",
                    "--owner",
                    fixture.owner,
                    *flags,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(process.stdout)

        dry_run = await repair_cli()
        assert dry_run["mode"] == "dry-run"
        planned = next(item for item in dry_run["messages"] if item["run_id"] == run["id"])
        assert planned["eligible"] == [stored["id"]] and planned["applied"] == []
        path.write_bytes(b"Explicit fixture corrupt-file check")
        corrupt = await repair_cli("--apply")
        rejected = next(item for item in corrupt["messages"] if item["run_id"] == run["id"])
        assert (
            rejected["unavailable_or_hash_mismatch"] == [stored["id"]] and rejected["applied"] == []
        )
        path.write_bytes(original)
        repaired = await repair_cli("--apply")
        actual = next(item for item in repaired["messages"] if item["run_id"] == run["id"])
        assert actual["applied"] == [stored["id"]]
        async with fixture.runtime.db.sessions() as session, session.begin():
            again = await repair_completed_images(
                session, fixture.owner, run["id"], apply=True, verified_artifact_ids={stored["id"]}
            )
            assert again["applied"] == []
            legacy_message = await session.get(MessageRow, assistant["id"])
            assert legacy_message is not None and legacy_message.attachment_ids == [stored["id"]]
        print(
            "PASS legacy repair dry-run is read-only; actual tool-derived IDs attach once, arbitrary uploaded IDs are excluded"
        )

        waiting_run = await fixture.run(agent, thread)
        waiting_context = await fixture.lease(waiting_run)
        waiting_artifact = await store_artifact(
            waiting_context.for_call("waiting-image"), "waiting.png", original, "image/png"
        )
        files.append(confined_path(context.artifact_root, waiting_artifact["payload"]["key"]))
        scripted[:] = [
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="clarify",
                        name="wait_for_input",
                        arguments={"question": "Which analysis should I continue?"},
                    )
                ]
            )
        ]
        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(waiting_context, registry, 90, 8)
        async with fixture.runtime.db.sessions() as session:
            waiting = await session.get(RunRow, waiting_run["id"])
            assert waiting is not None and waiting.status == "waiting_input"
            artifact = await session.get(ArtifactRow, waiting_artifact["id"])
            assert artifact is not None and artifact.state.get("delivered_message_id")
        admitted = await fixture.request(
            "POST",
            "/threads/" + thread["id"] + "/messages",
            {"content": "Continue now", "client_nonce": uuid4().hex},
        )
        assert waiting_run["id"] in admitted["run_ids"]
        resumed_context = await fixture.lease(waiting_run)
        scripted[:] = [ModelReply(text="Continued after clarification.")]
        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(resumed_context, registry, 90, 8)
        messages = cast(
            list[dict[str, Any]],
            await fixture.request("GET", "/threads/" + thread["id"] + "/messages"),
        )
        assert sum(waiting_artifact["id"] in message["attachment_ids"] for message in messages) == 1
        print(
            "PASS waiting-input delivery attaches once and resumed completion does not duplicate the image"
        )

        empty_run = await fixture.run(agent, thread)
        empty_context = await fixture.lease(empty_run)
        empty_artifact = await store_artifact(
            empty_context.for_call("empty-answer-image"), "empty.png", original, "image/png"
        )
        files.append(confined_path(context.artifact_root, empty_artifact["payload"]["key"]))
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, empty_context.lease, "", {})
        messages = cast(
            list[dict[str, Any]],
            await fixture.request("GET", "/threads/" + thread["id"] + "/messages"),
        )
        assert any(
            message["content"] == "" and message["attachment_ids"] == [empty_artifact["id"]]
            for message in messages
        )
        print("PASS attachment-only completion creates a real assistant message even with no text")
        svg_run = await fixture.run(agent, thread)
        svg_context = await fixture.lease(svg_run)
        legacy_svg = await registry.execute(
            ToolCall(
                id="pre-upgrade-svg",
                name="chart_snapshot",
                arguments={"chart_id": opened["chart"]["id"], "format": "svg"},
            ),
            svg_context,
        )
        svg_path = confined_path(context.artifact_root, legacy_svg["payload"]["key"])
        files.append(svg_path)
        svg_bytes = svg_path.read_bytes()
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(ArtifactRow, legacy_svg["id"])
            assert row is not None
            row.state = {}
        resumed_svg = await registry.execute(
            ToolCall(
                id="pre-upgrade-svg",
                name="chart_snapshot",
                arguments={"chart_id": opened["chart"]["id"]},
            ),
            svg_context,
        )
        assert (
            resumed_svg["id"] == legacy_svg["id"]
            and resumed_svg["payload"]["media_type"] == "image/svg+xml"
        )
        assert svg_path.read_bytes() == svg_bytes
        assert resumed_svg["state"]["producer_run_id"] == svg_run["id"]
        print(
            "PASS interrupted legacy SVG snapshot preserves its original bytes after PNG-default upgrade"
        )
    finally:
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()
        for path in files:
            path.unlink(missing_ok=True)
            path.parent.rmdir()


if __name__ == "__main__":
    asyncio.run(main())
