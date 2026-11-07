"""Bounded, timestamped tool evidence carried from this Agent's earlier Runs.

A new Run otherwise starts from the prose of earlier replies only, so a
follow-up re-fetches what was just observed or trusts its own paraphrase. This
projection reads the checkpoints of the Agent's most recent Runs in the same
thread and keeps the most relevant successful observations and every effect
identity, labelled historical: what was known then, never live broker truth.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, cast

from lonora_db.schema import RunRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..context_engine import IDENTITY_KEYS, OBSERVED_KEY, collect_identities

EVIDENCE_RUNS = 4
EVIDENCE_ENTRIES = 12
EVIDENCE_CHARS = 8000
PREVIEW_CHARS = 600
ARGUMENT_CHARS = 240
# Discovery, instructions, waits and self-notes are not evidence about the world.
SKIPPED_TOOLS = frozenset(
    {
        "tool_environment",
        "tool_call",
        "skills_list",
        "skill_view",
        "wait_for_input",
        "task_wait",
        "runtime_status",
        "memory_read",
        "memory_write",
        "scratchpad_write",
    }
)
EFFECT_TOOLS = frozenset({"trade_execute", "trade_close_positions", "goal_step_execute"})
EVIDENCE_NOTE = (
    "Tool results observed in this Agent's earlier Runs of this conversation, newest first "
    "within relevance. They are historical observations of what was known at observed_at, "
    "not live market or broker truth: prices, positions, orders and balances may have "
    "changed. Re-read before acting or before claiming current state; reuse them to avoid "
    "repeating a lookup only when their age is acceptable. A result_ref can be read again "
    "with artifact_read."
)


@dataclass(frozen=True)
class _Entry:
    key: str
    observed_at: str
    matched: bool
    payload: dict[str, Any]


def _terms(query: str) -> set[str]:
    return {term.casefold() for term in re.findall(r"[\w.#/-]{3,}", query)}


def _preview(result: dict[str, Any]) -> str:
    visible = {key: value for key, value in result.items() if not key.startswith("_")}
    text = json.dumps(visible, ensure_ascii=False, separators=(",", ":"), default=str)
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"


def _entries(run: RunRow, terms: set[str]) -> list[_Entry]:
    state: Any = run.execution_state
    if not isinstance(state, dict):
        return []
    state = cast(dict[str, Any], state)
    raw_messages: Any = state.get("messages", [])
    if not isinstance(raw_messages, list):
        return []
    observed_raw: Any = state.get(OBSERVED_KEY, {})
    observed = cast(dict[str, Any], observed_raw) if isinstance(observed_raw, dict) else {}
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    entries: list[_Entry] = []
    for raw in cast(list[Any], raw_messages):
        if not isinstance(raw, dict):
            continue
        message = cast(dict[str, Any], raw)
        for item in cast(list[Any], message.get("tool_calls") or []):
            if isinstance(item, dict):
                call = cast(dict[str, Any], item)
                arguments: Any = call.get("arguments", {})
                calls[str(call.get("id"))] = (
                    str(call.get("name", "")),
                    cast(dict[str, Any], arguments) if isinstance(arguments, dict) else {},
                )
        if message.get("role") != "tool":
            continue
        identifier = str(message.get("tool_call_id"))
        name, arguments = calls.get(identifier, ("", {}))
        if not name or name in SKIPPED_TOOLS:
            continue
        try:
            decoded: Any = json.loads(str(message.get("content", "")))
        except ValueError:
            continue
        if not isinstance(decoded, dict):
            continue
        result = cast(dict[str, Any], decoded)
        effect = name in EFFECT_TOOLS
        # Failed reads carry nothing to reuse; every effect outcome keeps its identity.
        if result.get("ok") is not True and not effect:
            continue
        found: dict[str, str] = {}
        collect_identities(result, found)
        argument_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        stamp = observed.get(identifier)
        payload: dict[str, Any] = {
            "tool": name,
            "arguments": argument_text
            if len(argument_text) <= ARGUMENT_CHARS
            else argument_text[:ARGUMENT_CHARS] + "…",
            "observed_at": stamp if isinstance(stamp, str) else run.updated_at.isoformat(),
            "time_basis": "observed" if isinstance(stamp, str) else "run_last_updated",
            "run_id": run.id,
            "ok": result.get("ok") is True,
        }
        if found:
            payload["identities"] = {
                key: value for key, value in found.items() if key in IDENTITY_KEYS
            }
        if isinstance(result.get("result_ref"), str):
            payload["result_ref"] = result["result_ref"]
        payload["result"] = _preview(result)
        haystack = (name + " " + argument_text + " " + payload["result"]).casefold()
        entries.append(
            _Entry(
                name + ":" + argument_text,
                str(payload["observed_at"]),
                effect or any(term in haystack for term in terms),
                payload,
            )
        )
    return entries


async def recent_tool_evidence(
    session: AsyncSession, agent_id: str, thread_id: str, current_run_id: str, query: str
) -> str:
    runs = (
        await session.scalars(
            select(RunRow)
            .where(
                RunRow.thread_id == thread_id,
                RunRow.agent_id == agent_id,
                RunRow.id != current_run_id,
                RunRow.status.in_(["completed", "failed", "cancelled"]),
            )
            .order_by(RunRow.updated_at.desc())
            .limit(EVIDENCE_RUNS)
        )
    ).all()
    terms = _terms(query)
    newest: dict[str, _Entry] = {}
    for run in runs:
        for entry in _entries(run, terms):
            # The newest observation of the same call supersedes older ones.
            if entry.key not in newest or entry.observed_at > newest[entry.key].observed_at:
                newest[entry.key] = entry
    ranked = sorted(newest.values(), key=lambda entry: (entry.matched, entry.observed_at))
    lines: list[str] = []
    size = len(EVIDENCE_NOTE)
    for entry in reversed(ranked):
        line = json.dumps(entry.payload, ensure_ascii=False, separators=(",", ":"))
        if len(lines) >= EVIDENCE_ENTRIES or size + len(line) + 1 > EVIDENCE_CHARS:
            break
        lines.append(line)
        size += len(line) + 1
    return EVIDENCE_NOTE + "\n" + "\n".join(lines) if lines else ""
