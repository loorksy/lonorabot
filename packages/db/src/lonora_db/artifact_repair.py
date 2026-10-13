"""Conservative repair of legacy generated images using recorded tool effects, never timestamps."""

import json
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .generated_artifacts import link_generated_artifacts
from .messages import message_data
from .schema import AgentRow, ArtifactRow, MessageRow, RunRow
from .transactions import owned_thread

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}


def recorded_image_effects(run: RunRow) -> dict[str, tuple[str, dict[str, Any]]]:
    effects: dict[str, tuple[str, dict[str, Any]]] = {}
    calls: set[str] = set()
    raw_messages = run.execution_state.get("messages")
    if not isinstance(raw_messages, list):
        return effects
    for raw in cast(list[Any], raw_messages):
        if not isinstance(raw, dict):
            continue
        message = cast(dict[str, Any], raw)
        if message.get("role") == "assistant":
            raw_calls = message.get("tool_calls", [])
            if not isinstance(raw_calls, list):
                continue
            for raw_call in cast(list[Any], raw_calls):
                if not isinstance(raw_call, dict):
                    continue
                call = cast(dict[str, Any], raw_call)
                if call.get("name") in {
                    "chart_snapshot",
                    "artifact_create",
                }:
                    identity = call.get("id")
                    if isinstance(identity, str) and 0 < len(identity) <= 256:
                        calls.add(identity)
        call_identity = message.get("tool_call_id")
        if (
            message.get("role") != "tool"
            or not isinstance(call_identity, str)
            or call_identity not in calls
        ):
            continue
        content = message.get("content")
        if not isinstance(content, str) or len(content) > 20000:
            continue
        try:
            decoded: Any = json.loads(content)
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        result = cast(dict[str, Any], decoded)
        payload = result.get("payload")
        call_id = str(message["tool_call_id"])
        # This is the legacy stable_id(run_id, call_id) UUID5 contract. Keep it
        # explicit here rather than creating a db -> session dependency cycle.
        expected_id = str(uuid5(NAMESPACE_URL, run.id + ":" + call_id))
        if (
            result.get("ok") is True
            and result.get("id") == expected_id
            and isinstance(payload, dict)
        ):
            data = cast(dict[str, Any], payload)
            media_type = data.get("media_type")
            if (
                isinstance(media_type, str)
                and media_type in IMAGE_TYPES
                and all(isinstance(data.get(key), str) for key in ("name", "key", "sha256"))
                and isinstance(data.get("size"), int)
            ):
                effects[expected_id] = (call_id, data)
    return effects


async def repair_completed_images(
    session: AsyncSession,
    owner_id: str,
    run_id: str,
    *,
    apply: bool = False,
    verified_artifact_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Apply only caller hash-verified files. The CLI defaults to a read-only plan."""
    run = await session.get(RunRow, run_id)
    if run is None:
        raise LonoraError("run_not_found", 404)
    thread = await owned_thread(session, owner_id, run.thread_id, lock=apply)
    if apply:
        run = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
        assert run is not None
    agent = await session.scalar(
        select(AgentRow).where(AgentRow.id == run.agent_id, AgentRow.owner_id == owner_id)
    )
    message_id = run.model_metadata.get("result_message_id")
    report: dict[str, Any] = {
        "run_id": run_id,
        "message_id": message_id,
        "candidates": [],
        "applied": [],
    }
    if run.status != "completed" or agent is None or not isinstance(message_id, str):
        return report
    message = await session.get(
        MessageRow, message_id, with_for_update=apply, populate_existing=True
    )
    if (
        message is None
        or message.thread_id != thread.id
        or message.agent_id != run.agent_id
        or message.role != "assistant"
        or message.content != run.result
    ):
        return report
    effects = recorded_image_effects(run)
    query = (
        select(ArtifactRow)
        .where(
            ArtifactRow.id.in_(effects),
            ArtifactRow.owner_id == owner_id,
            ArtifactRow.thread_id == thread.id,
            ArtifactRow.agent_id == run.agent_id,
        )
        .order_by(ArtifactRow.created_at, ArtifactRow.id)
    )
    if apply:
        query = query.with_for_update()
    artifacts = list(await session.scalars(query))
    candidates: list[ArtifactRow] = []
    for artifact in artifacts:
        call_id, recorded = effects[artifact.id]
        if any(
            artifact.payload.get(key) != recorded.get(key)
            for key in ("name", "key", "media_type", "size", "sha256")
        ):
            continue
        if artifact.state.get("producer_run_id") not in (None, run.id) or artifact.state.get(
            "delivered_message_id"
        ) not in (None, message.id):
            continue
        if artifact.id in message.attachment_ids:
            continue
        candidates.append(artifact)
        report["candidates"].append(
            {
                "artifact_id": artifact.id,
                "key": artifact.payload["key"],
                "sha256": artifact.payload["sha256"],
            }
        )
        if apply and artifact.id in (verified_artifact_ids or set()):
            artifact.state = {
                **artifact.state,
                "producer_run_id": run.id,
                "producer_call_id": call_id,
            }
    if apply:
        approved = [
            artifact for artifact in candidates if artifact.id in (verified_artifact_ids or set())
        ]
        link_generated_artifacts(message, approved)
        if approved:
            report["applied"] = [artifact.id for artifact in approved]
            emit(
                session,
                owner_id,
                "message.updated",
                thread_id=thread.id,
                agent_id=run.agent_id,
                run_id=run.id,
                payload=message_data(message),
            )
    return report
