"""Workspace file -> immutable attachment -> actual vision context -> chat delivery."""

import asyncio
import base64
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import ArtifactRow, MessageRow, RunRow, TradingJournalRow
from lonora_security.runtime_storage import confined_path
from lonora_tools import workspace_export
from lonora_tools.loader import load_tools
from PIL import Image
from sqlalchemy import func, select
from workspace_fake import FakeWorkspace


async def main() -> None:
    fixture = await Fixture().open()
    original_root = fixture.settings.artifact_root
    with TemporaryDirectory(prefix="lonora-workspace-artifacts-") as directory:
        try:
            fixture.settings.artifact_root = Path(directory)
            agent = await fixture.agent("Workspace delivery")
            thread = await fixture.conversation(agent)
            context = await fixture.lease(await fixture.run(agent, thread))
            image = BytesIO()
            Image.new("RGB", (8, 6), (11, 77, 123)).save(image, format="PNG")
            png = image.getvalue()

            workspace = FakeWorkspace()
            workspace.files[(context.agent_id, "result.md")] = b"# Original analysis"
            workspace.files[(context.agent_id, "result.png")] = png
            context = replace(context, workspace=workspace.client())
            registry = load_tools()

            async def call(identity: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
                return await registry.execute(
                    ToolCall(id=identity, name=name, arguments=args), context
                )

            async def refused(identity: str, args: dict[str, Any], code: str) -> None:
                try:
                    await call(identity, "workspace_export", args)
                except LonoraError as error:
                    assert error.code == code, error.code
                else:
                    raise AssertionError("Expected " + code)

            async with context.db.sessions() as session:
                journal_before = await session.scalar(
                    select(func.count()).select_from(TradingJournalRow)
                )
            image_export = await call("image-export", "workspace_export", {"path": "result.png"})
            report = await call(
                "report-export",
                "workspace_export",
                {"path": "result.md", "name": "analysis.md"},
            )
            assert image_export["payload"]["media_type"] == "image/png"
            assert report["state"]["workspace_source"]["path"] == "result.md"
            assert "delivered_message_id" not in image_export["state"]
            assert "image_observation" not in image_export, "Export faked visual inspection"
            # The file changes; a replay still returns the attachment the call made.
            workspace.files[(context.agent_id, "result.md")] = b"# New analysis"
            assert (
                await call(
                    "report-export",
                    "workspace_export",
                    {"path": "result.md", "name": "analysis.md"},
                )
                == report
            )
            await refused(
                "report-export",
                {"path": "result.md", "name": "other.md"},
                "workspace_export_conflict",
            )
            await refused(
                "mislabel",
                {"path": "result.png", "name": "analysis.jpg"},
                "workspace_export_format_mismatch",
            )
            await refused(
                "unsafe-name",
                {"path": "result.md", "name": "../analysis.md"},
                "workspace_export_filename_invalid",
            )
            await refused("missing-source", {"path": "absent.md"}, "workspace_file_unreadable")
            await refused(
                "binary-source", {"path": "result.exe"}, "workspace_export_format_unsupported"
            )

            # Verify integrity before replay, even when the filesystem advanced.
            report_path = confined_path(context.artifact_root, report["payload"]["key"])
            await asyncio.to_thread(report_path.write_bytes, b"corrupted")
            await refused(
                "report-export",
                {"path": "result.md", "name": "analysis.md"},
                "artifact_integrity_failed",
            )
            await asyncio.to_thread(report_path.write_bytes, b"# Original analysis")

            original_store = workspace_export.store_artifact

            async def replaced_before_store(
                actor: Any, *args: Any, **kwargs: Any
            ) -> dict[str, Any]:
                async with actor.db.sessions() as session, session.begin():
                    run = await session.get(RunRow, actor.lease.run_id)
                    assert run
                    run.lease_fence += 1
                return await original_store(actor, *args, **kwargs)

            with patch.object(workspace_export, "store_artifact", replaced_before_store):
                await refused("fenced-export", {"path": "result.md"}, "stale_lease")
            fenced_path = confined_path(
                context.artifact_root, context.for_call("fenced-export").resource_id + "/result.md"
            )
            assert not await asyncio.to_thread(fenced_path.exists)
            async with context.db.sessions() as session:
                assert (
                    await session.get(ArtifactRow, context.for_call("fenced-export").resource_id)
                    is None
                )
            context = replace(
                await fixture.lease(
                    {
                        "id": context.lease.run_id,
                        "agent_id": context.agent_id,
                        "thread_id": context.thread_id,
                    }
                ),
                workspace=context.workspace,
            )
            await asyncio.to_thread(report_path.unlink)
            await refused(
                "report-export",
                {"path": "result.md", "name": "analysis.md"},
                "artifact_file_missing",
            )
            await asyncio.to_thread(report_path.write_bytes, b"# Original analysis")

            rounds = 0

            async def model(
                capability: Capability, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
            ):
                nonlocal rounds
                rounds += 1
                if rounds == 1:
                    reply = ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="inspect-pixels",
                                name="artifact_read",
                                arguments={"artifact_id": image_export["id"], "view_image": True},
                            )
                        ]
                    )
                else:
                    assert capability is Capability.VISION
                    observation = next(
                        message
                        for message in messages
                        if message.images and message.context_origin == "tool_observation"
                    )
                    observed = base64.b64decode(observation.images[0].split(",", 1)[1])
                    assert observed == png
                    with Image.open(BytesIO(observed)) as pixels:
                        assert pixels.getpixel((0, 0)) == (11, 77, 123)
                    reply = ModelReply(text="The analysis and image are attached.")
                return reply, ModelSelection(provider="openai", model="scripted-workspace-vision")

            with patch.object(context.router, "complete", model):
                await execute_run(context, registry, 120, 5)
            async with context.db.sessions() as session:
                delivered = await session.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.thread_id == context.thread_id, MessageRow.role == "assistant"
                    )
                    .order_by(MessageRow.seq.desc())
                    .limit(1)
                )
                assert delivered and set(delivered.attachment_ids) == {
                    image_export["id"],
                    report["id"],
                }
                for artifact_id in delivered.attachment_ids:
                    artifact = await session.get(ArtifactRow, artifact_id)
                    assert artifact and artifact.state["delivered_message_id"] == delivered.id
                assert (
                    await session.scalar(select(func.count()).select_from(TradingJournalRow))
                    == journal_before
                )
            for saved, expected in ((image_export, png), (report, b"# Original analysis")):
                downloaded = await fixture.client.get("/api/artifacts/" + saved["id"] + "/file")
                assert downloaded.status_code == 200 and downloaded.content == expected
            assert rounds == 2
            print(
                "PASS workspace report/image export from the file system, immutable replay, integrity and scope failures, actual vision pixels, canonical attachments/downloads and zero financial effects"
            )
        finally:
            fixture.settings.artifact_root = original_root
            await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
