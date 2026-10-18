"""Private, bounded observations backed by the existing artifact store.

These are receipts for observations, not permission to repeat an effect. Retention
is owner-managed; deleting a file never grants mutation replay permission.
"""

import hashlib
import json
from typing import Any

from lonora_adapter_kit.types import ToolCall
from lonora_core.attachments import MAX_ATTACHMENT_BYTES
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.runs import require_lease
from lonora_security.runtime_storage import confined_path
from lonora_security.secrets import redact
from lonora_session.idempotency import request_hash, stable_id

from .artifacts import store_artifact
from .context import ToolContext


def result_identity(context: ToolContext, call: ToolCall) -> str:
    return stable_id(context.lease.run_id, "tool-result:" + call.id)


def call_hash(call: ToolCall) -> str:
    return request_hash({"name": call.name, "arguments": call.arguments})


async def store_result(
    context: ToolContext, call: ToolCall, result: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    projected = redact(result)
    content = json.dumps(projected, ensure_ascii=False).encode("utf-8")
    # Separate namespace from artifacts intentionally created by this tool call.
    internal_context = context.for_call("tool-result:" + call.id)
    pointer = {
        "result_ref": result_identity(context, call),
        "result_format": "redacted_json",
        "result_retention": "owner_managed",
        "result_persisted": True,
        "result_read_tool": "artifact_read",
    }
    bounded = {**redact(summary), **pointer}
    bounded["recovery"] = (
        summary.get("recovery")
        if summary.get("status") == "ambiguous"
        else {
            "category": "result_too_large",
            "next_action": "read_stored_result",
            "schema_tool": "artifact_read",
        }
    )
    # The file and receipt metadata must commit together under the same fence.
    # store_artifact normally owns its transaction, so pass receipt state into it.
    await store_artifact(
        internal_context,
        "tool-result.json",
        content,
        "application/json",
        receipt_state={
            "internal_tool_result": True,
            "producer_call_id": call.id,
            "tool_name": call.name,
            "request_hash": call_hash(call),
            "result_summary": bounded,
            "result_format": "redacted_json",
            "retention": "owner_managed",
        },
    )
    return bounded


async def stored_result(context: ToolContext, call: ToolCall) -> dict[str, Any] | None:
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        row = await session.get(ArtifactRepository.row_type, result_identity(context, call))
        if row is None:
            return None
        if (
            row.owner_id != context.owner_id
            or row.agent_id != context.agent_id
            or row.thread_id != context.thread_id
            or row.state.get("internal_tool_result") is not True
            or row.state.get("producer_run_id") != context.lease.run_id
            or row.state.get("producer_call_id") != call.id
            or row.state.get("request_hash") != call_hash(call)
        ):
            raise LonoraError("tool_result_identity_conflict", 409)
        result = dict(row.state["result_summary"])
        path = confined_path(context.artifact_root, row.payload["key"])
        # Missing/corrupt data cannot make an already completed effect replayable.
        try:
            size = path.stat().st_size
            if size == row.payload["size"] and size <= MAX_ATTACHMENT_BYTES:
                with path.open("rb") as source:
                    content = source.read(MAX_ATTACHMENT_BYTES + 1)
                valid = (
                    len(content) == size
                    and hashlib.sha256(content).hexdigest() == row.payload["sha256"]
                )
            else:
                valid = False
        except OSError:
            valid = False
        if not valid:
            result["result_storage_error"] = "tool_result_file_unavailable"
        return result
