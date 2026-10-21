"""Restrict public completion claims when the server lacks independent evidence."""

import json
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage

FINANCIAL_CALLS = {"trade_execute", "trade_close_positions", "goal_step_execute"}


def public_broker_ids(messages: list[ModelMessage]) -> set[str]:
    """Only exact verified broker receipt IDs, never private envelope resource IDs."""
    calls = {
        call.id: call.name
        for message in messages
        for call in message.tool_calls
        if call.name in FINANCIAL_CALLS | {"account_read"}
    }
    identities: set[str] = set()
    for message in messages:
        if message.role != "tool" or message.tool_call_id not in calls:
            continue
        try:
            raw = json.loads(message.content)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        data = cast(dict[str, Any], raw)
        if calls[message.tool_call_id] == "account_read":
            for name in ("positions", "orders"):
                targets = data.get(name, [])
                if isinstance(targets, list):
                    for target in cast(list[Any], targets):
                        identity = (
                            cast(dict[str, Any], target).get("id")
                            if isinstance(target, dict)
                            else None
                        )
                        if isinstance(identity, str) and identity:
                            identities.add(identity)
            continue
        rows = data.get("results", [data])
        if not isinstance(rows, list):
            continue
        for candidate in cast(list[Any], rows):
            if not isinstance(candidate, dict):
                continue
            row = cast(dict[str, Any], candidate)
            details: Any = row.get("details", {})
            if row.get("status") != "confirmed" or not isinstance(details, dict):
                continue
            details = cast(dict[str, Any], details)
            verification: Any = details.get("verification", {})
            if (
                not isinstance(verification, dict)
                or cast(dict[str, Any], verification).get("status") != "verified"
            ):
                continue
            for identity in [
                row.get("broker_id"),
                *[details.get(key) for key in ("position_id", "order_id", "deal_id")],
            ]:
                if isinstance(identity, str) and identity:
                    identities.add(identity)
    return identities


def unverified_financial_result(messages: list[ModelMessage]) -> str | None:
    names = {
        call.id: call.name
        for message in messages
        for call in message.tool_calls
        if call.name in FINANCIAL_CALLS
    }
    # The latest owner message begins a new request, so an old unverified result
    # cannot replace an unrelated answer on a subsequent turn.
    for message in reversed(messages):
        if message.role == "user":
            break
        if message.role != "tool" or message.tool_call_id not in names:
            continue
        try:
            payload = json.loads(message.content)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        data = cast(dict[str, Any], payload)
        results = data.get("results", [data])
        if not isinstance(results, list):
            continue
        pending = False
        for raw in cast(list[Any], results):
            if not isinstance(raw, dict):
                continue
            row = cast(dict[str, Any], raw)
            details = row.get("details")
            verification = (
                cast(dict[str, Any], details).get("verification")
                if isinstance(details, dict)
                else None
            )
            verified = (
                isinstance(verification, dict)
                and cast(dict[str, Any], verification).get("status") == "verified"
            )
            pending = pending or (row.get("status") == "confirmed" and not verified)
        if pending:
            arabic = True
            for owner in reversed(messages):
                if owner.role != "user":
                    continue
                if re.search(r"[\u0620-\u064a]", owner.content):
                    break
                if " " in owner.content and len(re.findall(r"[A-Za-z]", owner.content)) >= 8:
                    arabic = False
                    break
            return (
                "أقرّ الوسيط بالطلب، لكن التحقق المستقل من نتيجته لم يكتمل بعد. لن أكرر الإرسال."
                if arabic
                else "The broker acknowledged the request, but its resulting state is not yet independently verified. I will not resend it."
            )
    return None
