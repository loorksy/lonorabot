"""Durable call-intent markers and closing of unexecuted proposals.

``inflight_calls`` replaces the single ``inflight`` slot of earlier releases
with one entry per call. A serial call still writes that slot too, so a rolled
back worker cannot replay a mutation it does not see in the per-call set.
"""

import json
from collections.abc import Sequence
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_db.runs import require_lease
from lonora_tools.context import ToolContext

from .environment import route_key

INFLIGHT_KEY = "inflight_calls"


def close_unexecuted(
    messages: list[ModelMessage], pending: list[ToolCall], reason: str | None, *, code: str = ""
) -> None:
    """Answer every unexecuted call so the tool exchange stays protocol-complete."""
    for sibling in pending:
        result: dict[str, Any] = {"ok": False, "code": code or "tool_call_superseded"}
        if reason:
            result["reason"] = reason
        messages.append(
            ModelMessage(role="tool", tool_call_id=sibling.id, content=json.dumps(result))
        )
    pending.clear()


async def cancel_superseded_approvals(context: ToolContext, calls: Sequence[ToolCall]) -> None:
    """A superseded proposal must never leave a live approval behind."""
    if not calls:
        return
    from lonora_db.schema import TradeApprovalRow
    from lonora_db.trade_approvals import approval_event
    from lonora_session.idempotency import stable_id

    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        for superseded_call in calls:
            approval = await session.get(
                TradeApprovalRow,
                stable_id(context.lease.run_id, "approval:" + superseded_call.id),
                with_for_update=True,
            )
            if approval and approval.status in {"pending", "approved"}:
                approval.status = "cancelled"
                approval_event(session, approval)


def inflight_ids(environment: dict[str, Any]) -> set[str]:
    """Calls whose handler may have crossed an effect boundary before a crash.

    Reads the per-call set and the single slot written by earlier releases.
    """
    identifiers: set[str] = set()
    legacy = environment.get("inflight")
    if isinstance(legacy, dict) and isinstance(cast(dict[str, Any], legacy).get("call_id"), str):
        identifiers.add(cast(str, cast(dict[str, Any], legacy)["call_id"]))
    entries = environment.get(INFLIGHT_KEY)
    if isinstance(entries, list):
        for entry in cast(list[Any], entries):
            if isinstance(entry, dict) and isinstance(
                identifier := cast(dict[str, Any], entry).get("call_id"), str
            ):
                identifiers.add(identifier)
    return identifiers


def mark_inflight(environment: dict[str, Any], calls: Sequence[ToolCall]) -> None:
    current = {call.id for call in calls}
    previous = environment.get(INFLIGHT_KEY)
    retained: list[dict[str, Any]] = [
        cast(dict[str, Any], entry)
        for entry in (cast(list[Any], previous) if isinstance(previous, list) else [])
        if isinstance(entry, dict) and cast(dict[str, Any], entry).get("call_id") not in current
    ]
    entries = [
        {"call_id": call.id, "route_key": route_key(call), "tool": call.name} for call in calls
    ]
    environment[INFLIGHT_KEY] = retained + entries
    if len(calls) == 1:
        # The single slot keeps a rolled-back worker from replaying a mutation
        # it cannot see in the per-call set.
        environment["inflight"] = entries[0]


def clear_inflight(environment: dict[str, Any], call_ids: set[str]) -> None:
    previous = environment.get(INFLIGHT_KEY)
    if isinstance(previous, list):
        remaining: list[dict[str, Any]] = [
            cast(dict[str, Any], entry)
            for entry in cast(list[Any], previous)
            if isinstance(entry, dict)
            and cast(dict[str, Any], entry).get("call_id") not in call_ids
        ]
        if remaining:
            environment[INFLIGHT_KEY] = remaining
        else:
            environment.pop(INFLIGHT_KEY, None)
    legacy = environment.get("inflight")
    if not isinstance(legacy, dict) or cast(dict[str, Any], legacy).get("call_id") in call_ids:
        environment.pop("inflight", None)


def start_budget_epoch(state: dict[str, Any]) -> None:
    """Real owner input at a limit authorizes one new bounded budget."""
    state["prior_attempt_rounds"] = int(state.get("prior_attempt_rounds", 0)) + int(
        state.get("rounds", 0)
    )
    state["rounds"] = 0
    continuation = state.get("task_continuation")
    if isinstance(continuation, dict):
        cast(dict[str, Any], continuation)["slice"] = 1
    for key in ("limit_exit", "exit_reason", "budget_warned"):
        state.pop(key, None)
