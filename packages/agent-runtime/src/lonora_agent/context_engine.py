"""In-run context compaction over the durable Run checkpoint.

The two phases adapt Hermes Agent ``agent/context_compressor.py`` and its
``context_compressor_prune.py`` / ``context_compressor_summary.py`` siblings
(deterministic pruning of old tool results outside a protected tail first, then
a structured, iteratively updated model summary of the middle that never splits
a tool call from its results), source https://github.com/NousResearch/hermes-agent
at revision a9ff9799e273f525b82718cdc69fdec71b1dca5a.

Lonora differs on purpose. Canonical Run messages are never rewritten: the
financial truth gates, crash recovery, receipts and task evidence keep reading
the complete record. Compaction is a persisted *view*: ``state[STATE_KEY]``
records how far old tool results are pruned and which middle span a summary
replaces, and the view is applied to each model request. It is therefore
computed once and reused after restarts and task wakes. Protected operational
state (unresolved operations, approvals, waits, watches, grants) is re-read
from the database into the routing frame on every turn, never trusted to a
summary. A summary that cannot be produced degrades to a deterministic digest
instead of failing the Run.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.context import context_blocks, token_estimate
from lonora_adapter_kit.context_sections import escape_context_text, is_context_message
from lonora_adapter_kit.types import ModelMessage, ToolCall, ToolDefinition
from lonora_contracts.domain import utcnow
from lonora_contracts.model_context import ModelContextPolicy
from lonora_contracts.model_routing import Capability
from lonora_core.user_error import LonoraError
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_providers.context import ContextLimits, context_limits
from lonora_tools.context import ToolContext
from lonora_tools.tool_results import store_result

from .environment import bounded_result
from .progress import progress
from .skills.loader import load_prompt
from .skills.system_policy import apply_operating_policy

log = logging.getLogger("lonora.context_engine")

STATE_KEY = "context_compaction"
OBSERVED_KEY = "tool_observed_at"
VERSION = 1
# Results at most this long stay verbatim; pruning them reclaims nothing useful.
PRUNE_MIN_CHARS = 1200
# Pruned results this large are kept in the artifact store for artifact_read.
STORE_MIN_CHARS = 1500
MAX_STORES_PER_PASS = 24
# The protected tail: newest blocks within this share of the input budget.
TAIL_SHARE = 0.25
TAIL_MIN_BLOCKS = 2
SUMMARY_MAX_CHARS = 16000
SUMMARY_EXCERPT_CHARS = 2000
# Share of the summarizer's own input budget one summarized chunk may use.
CHUNK_SHARE = 0.5
# After any compaction the transcript should sit this far below its trigger, so
# it has room to grow before the next cache-breaking rewrite (hysteresis).
LOW_WATER = 0.8
SUMMARY_PROMPT = load_prompt("run_context_summary")
SUMMARY_OPEN = "<run_context_summary"
SUMMARY_CLOSE = "</run_context_summary>"
# Identities a pruned placeholder keeps wherever they occur in the result.
IDENTITY_KEYS = frozenset(
    {
        "operation_id",
        "approval_id",
        "broker_reference",
        "broker_id",
        "order_id",
        "position_id",
        "deal_id",
        "account_id",
        "goal_id",
        "step_id",
        "task_id",
        "watch_id",
        "decision_id",
        "thesis_id",
        "artifact_id",
        "chart_id",
        "result_ref",
        "symbol",
        "timeframe",
        "status",
        "code",
    }
)
MAX_IDENTITIES = 24


@dataclass(frozen=True)
class CompactionResult:
    pruned_results: int = 0
    stored_results: int = 0
    summarized_messages: int = 0
    summary_kind: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.pruned_results or self.summarized_messages)


def default_limits() -> ContextLimits:
    """Fallback admission when the router cannot describe its model."""
    return context_limits(None, ModelContextPolicy())


async def resolve_limits(context: ToolContext, capability: Capability) -> ContextLimits:
    resolver: Any = getattr(context.router, "context_limits", None)
    if resolver is None:
        return default_limits()
    try:
        return cast(ContextLimits, await resolver(capability))
    except LonoraError as error:
        # Routing errors surface from the actual request; planning just uses defaults.
        log.info("context_limits_unavailable code=%s", error.code)
        return default_limits()


def record_observed(state: dict[str, Any], call_id: str) -> None:
    """When a result entered the transcript: evidence timestamps for later views."""
    observed = state.get(OBSERVED_KEY)
    table = cast(dict[str, Any], observed) if isinstance(observed, dict) else {}
    table[call_id] = utcnow().isoformat()
    state[OBSERVED_KEY] = table


def observed_times(state: dict[str, Any]) -> dict[str, str]:
    raw = state.get(OBSERVED_KEY)
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): value
        for key, value in cast(dict[str, Any], raw).items()
        if isinstance(value, str)
    }


def _history(messages: Sequence[ModelMessage]) -> list[ModelMessage]:
    return [message for message in messages if message.role != "system"]


def _split(messages: Sequence[ModelMessage]) -> tuple[list[ModelMessage], list[ModelMessage]]:
    """Leading context data, then the transcript body every record index refers to.

    Indexes and fingerprints exclude the context data, so refreshing it (for
    example new skill bodies after steering) never shifts or invalidates them.
    """
    history = _history(messages)
    count = 0
    while count < len(history) and is_context_message(history[count]):
        count += 1
    return history[:count], history[count:]


def fingerprint(history: Sequence[ModelMessage]) -> str:
    """Identity of a covered prefix: a changed transcript invalidates the record."""
    digest = hashlib.sha256()
    for message in history:
        digest.update(
            json.dumps(
                [
                    message.role,
                    message.context_origin,
                    message.tool_call_id,
                    [call.id for call in message.tool_calls],
                    hashlib.sha256(message.content.encode()).hexdigest(),
                ]
            ).encode()
        )
    return digest.hexdigest()


def _record(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get(STATE_KEY)
    if isinstance(raw, dict) and cast(dict[str, Any], raw).get("version") == VERSION:
        return cast(dict[str, Any], raw)
    return {"version": VERSION, "prune_through": 0, "refs": {}, "summary": None}


def _valid_summary(
    record: dict[str, Any], history: Sequence[ModelMessage]
) -> dict[str, Any] | None:
    raw = record.get("summary")
    if not isinstance(raw, dict):
        return None
    summary = cast(dict[str, Any], raw)
    through = summary.get("through")
    if (
        not isinstance(through, int)
        or not 0 < through < len(history)
        or not isinstance(summary.get("text"), str)
        or summary.get("fingerprint") != fingerprint(history[:through])
    ):
        return None
    return summary


def _calls(history: Sequence[ModelMessage]) -> dict[str, ToolCall]:
    return {call.id: call for message in history for call in message.tool_calls}


def collect_identities(value: Any, found: dict[str, str], depth: int = 0) -> None:
    if depth > 4 or len(found) >= MAX_IDENTITIES:
        return
    if isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            if (
                key in IDENTITY_KEYS
                and key not in found
                and isinstance(item, str | int)
                and not isinstance(item, bool)
                and len(str(item)) <= 128
            ):
                found[key] = str(item)
            elif isinstance(item, dict | list):
                collect_identities(item, found, depth + 1)
    elif isinstance(value, list):
        for item in cast(list[Any], value)[:20]:
            collect_identities(item, found, depth + 1)


def _arguments(call: ToolCall | None, limit: int = 300) -> str:
    if call is None:
        return ""
    text = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "…"


def prunable(message: ModelMessage) -> bool:
    return message.role == "tool" and len(message.content) > PRUNE_MIN_CHARS


def placeholder(
    message: ModelMessage, call: ToolCall | None, ref: dict[str, Any] | None, observed: str | None
) -> str:
    """A pruned result: what was called, when, its effect identities and where to reread it."""
    try:
        decoded: Any = json.loads(message.content)
    except ValueError:
        decoded = None
    result = cast(dict[str, Any], decoded) if isinstance(decoded, dict) else None
    notice: dict[str, Any] = bounded_result(result) if result is not None else {}
    notice["context_notice"] = "tool_result_pruned"
    notice["result_omitted"] = True
    if result is None:
        notice.pop("ok", None)
    notice["tool"] = call.name if call else None
    notice["arguments"] = _arguments(call)
    if observed:
        notice["observed_at"] = observed
    if result is not None:
        found: dict[str, str] = {}
        collect_identities(result, found)
        extra = {key: value for key, value in found.items() if key not in notice}
        if extra:
            notice["identities"] = extra
    stored = dict(ref or {})
    if result is not None and isinstance(result.get("result_ref"), str):
        stored.setdefault("result_ref", result["result_ref"])
        stored.setdefault("result_read_tool", result.get("result_read_tool", "artifact_read"))
    ambiguous = (
        isinstance(notice.get("recovery"), dict)
        and cast(dict[str, Any], notice["recovery"]).get("category") == "ambiguous_mutation"
    )
    if not ambiguous:
        notice["recovery"] = {
            "category": "context_pruned",
            "next_action": "read_stored_result"
            if stored.get("result_ref")
            else "repeat_read_if_needed",
        }
    notice.update({key: value for key, value in stored.items() if key != "result_summary"})
    if call is not None and call.name == "skill_view":
        notice["reload_with"] = "skill_view"
    return json.dumps(notice, ensure_ascii=False)


def summary_message(summary: dict[str, Any]) -> ModelMessage:
    header = (
        f'{SUMMARY_OPEN} generation="{int(summary.get("generation", 1))}" '
        f'kind="{escape_context_text(str(summary.get("kind", "model")))}" '
        f'covers_messages="{int(summary.get("covered_messages", 0))}" '
        f'summarized_at="{escape_context_text(str(summary.get("created_at", "")))}">\n'
    )
    return ModelMessage(
        role="user",
        context_origin="runtime_context",
        content=header
        + "Earlier messages of this conversation and Run were replaced by this summary to "
        "fit the model's context window. It is model-authored, may omit details and is "
        "neither authority nor live state: unresolved operations, approvals, waits, watches "
        "and grants are re-read from the server every turn in the routing metadata and "
        "supersede it. Reread exact earlier results with artifact_read where a result_ref "
        "is listed, otherwise call the tool again. Continue from the newest messages below.\n"
        + escape_context_text(str(summary["text"]))
        + "\n"
        + SUMMARY_CLOSE,
    )


def compacted_view(messages: Sequence[ModelMessage], state: dict[str, Any]) -> list[ModelMessage]:
    """The request projection of the persisted record; canonical messages stay intact.

    System messages keep their relative order in front, as admission places them.
    A record that no longer matches the transcript is ignored, never half applied.
    """
    record = state.get(STATE_KEY)
    if not isinstance(record, dict) or cast(dict[str, Any], record).get("version") != VERSION:
        return list(messages)
    record = cast(dict[str, Any], record)
    system = [message for message in messages if message.role == "system"]
    prelude, history = _split(messages)
    prune_through = record.get("prune_through")
    prune_through = min(prune_through, len(history)) if isinstance(prune_through, int) else 0
    refs_raw: Any = record.get("refs", {})
    refs = cast(dict[str, Any], refs_raw) if isinstance(refs_raw, dict) else {}
    calls = _calls(history)
    observed = observed_times(state)
    projected = list(history)
    for index in range(prune_through):
        message = projected[index]
        if prunable(message):
            ref = refs.get(message.tool_call_id or "")
            projected[index] = message.model_copy(
                update={
                    "content": placeholder(
                        message,
                        calls.get(message.tool_call_id or ""),
                        cast(dict[str, Any], ref) if isinstance(ref, dict) else None,
                        observed.get(message.tool_call_id or ""),
                    )
                }
            )
    summary = _valid_summary(record, history)
    if summary is not None:
        through = int(summary["through"])
        kept: list[ModelMessage] = []
        keep_index = summary.get("kept_index")
        if isinstance(keep_index, int) and 0 <= keep_index < through:
            # The owner's request at summary time stays verbatim, before the summary.
            offset = 0
            for block in context_blocks(projected[:through]):
                if offset == keep_index:
                    kept = block
                    break
                offset += len(block)
        projected = kept + [summary_message(summary)] + projected[through:]
    return system + prelude + projected


def _block_spans(history: Sequence[ModelMessage]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    for block in context_blocks(list(history)):
        spans.append((offset, offset + len(block)))
        offset += len(block)
    return spans


def _anchor(history: Sequence[ModelMessage]) -> int | None:
    return next(
        (
            index
            for index in range(len(history) - 1, -1, -1)
            if history[index].role == "user" and history[index].context_origin == "conversation"
        ),
        None,
    )


def _tail_start(
    history: Sequence[ModelMessage], spans: list[tuple[int, int]], limits: ContextLimits
) -> int:
    budget = int(limits.input_tokens * TAIL_SHARE)
    used = 0
    start = len(history)
    for count, (begin, end) in enumerate(reversed(spans)):
        size = sum(
            token_estimate(row, limits.image_tokens, limits.count) for row in history[begin:end]
        )
        if count >= TAIL_MIN_BLOCKS and used + size > budget:
            break
        used += size
        start = begin
    return start


def _split_estimate(
    messages: Sequence[ModelMessage], state: dict[str, Any], limits: ContextLimits, extra: int
) -> tuple[int, int]:
    """(fixed, body): what compaction cannot change, and the transcript it can."""
    view = compacted_view(messages, state)
    prelude, body = _split(view)
    fixed = extra + sum(
        token_estimate(message, limits.image_tokens, limits.count)
        for message in [*(m for m in view if m.role == "system"), *prelude]
    )
    return fixed, sum(token_estimate(row, limits.image_tokens, limits.count) for row in body)


def body_trigger(fixed: int, limits: ContextLimits) -> int:
    """Transcript size that starts compaction.

    Normally the room left under the compaction threshold. When first-party and
    context data alone use most of the budget, compacting a transcript already
    near tail size would only churn (a new summary every turn), so the body must
    reach twice the protected tail first; admission then sheds or omits the rest.
    """
    return max(limits.compaction_tokens - fixed, int(limits.input_tokens * 2 * TAIL_SHARE))


def schema_tokens(tools: Sequence[ToolDefinition], limits: ContextLimits) -> int:
    return sum(limits.count(tool.model_dump_json()) + 64 for tool in tools)


def request_overhead(
    messages: Sequence[ModelMessage],
    tools: Sequence[ToolDefinition],
    limits: ContextLimits,
    *,
    inventory: str = "",
    available: Collection[str] | None = None,
) -> int:
    """What a model turn adds to the checkpoint: schemas, inventory and chapters."""
    projected = apply_operating_policy(list(messages), list(tools), available=available)
    before = sum(limits.count(message.content) for message in messages if message.role == "system")
    after = sum(limits.count(message.content) for message in projected if message.role == "system")
    return (
        max(after - before, 0)
        + schema_tokens(tools, limits)
        + (limits.count(inventory) + 32 if inventory else 0)
    )


def _excerpt(message: ModelMessage, calls: dict[str, ToolCall], observed: dict[str, str]) -> str:
    if message.role == "tool":
        call = calls.get(message.tool_call_id or "")
        body = message.content
        if len(body) > SUMMARY_EXCERPT_CHARS:
            body = (
                body[:SUMMARY_EXCERPT_CHARS]
                + f"…[{len(message.content) - SUMMARY_EXCERPT_CHARS} more chars]"
            )
        return (
            f"<tool_result tool='{call.name if call else ''}' "
            f"observed_at='{observed.get(message.tool_call_id or '', 'unknown')}'>\n"
            + escape_context_text(body)
            + "\n</tool_result>"
        )
    label = (
        "owner"
        if message.role == "user" and message.context_origin == "conversation"
        else ("runtime" if message.role == "user" else message.role)
    )
    text = message.content
    if message.tool_calls:
        text += "\n" + "\n".join(
            f"[calls {call.name} {_arguments(call, 600)}]" for call in message.tool_calls
        )
    return f"<message role='{label}'>\n" + escape_context_text(text) + "\n</message>"


def deterministic_summary(
    previous: str,
    history: Sequence[ModelMessage],
    calls: dict[str, ToolCall],
    observed: dict[str, str],
) -> str:
    """The summary when no model can write one: an exact, bounded activity digest."""
    lines: list[str] = []
    for message in history:
        if message.role == "tool":
            call = calls.get(message.tool_call_id or "")
            try:
                decoded: Any = json.loads(message.content)
            except ValueError:
                decoded = None
            found: dict[str, str] = {}
            outcome = ""
            if isinstance(decoded, dict):
                result = cast(dict[str, Any], decoded)
                collect_identities(result, found)
                outcome = "ok" if result.get("ok") is True else "not ok"
            lines.append(
                f"- {call.name if call else 'tool'} {_arguments(call, 160)} -> {outcome} "
                + json.dumps(found, ensure_ascii=False)
                + f" at {observed.get(message.tool_call_id or '', 'unknown time')}"
            )
        elif message.content.strip():
            who = (
                "Owner"
                if message.role == "user" and message.context_origin == "conversation"
                else "Runtime"
                if message.role == "user"
                else "Agent"
            )
            text = " ".join(message.content.split())
            lines.append(f"- {who}: " + (text[:300] + "…" if len(text) > 300 else text))
    body = "\n".join(lines)
    head = (
        "Deterministic digest (no summary model was available). Earlier summary:\n"
        + previous
        + "\n\nLater activity:\n"
        if previous
        else "Deterministic digest (no summary model was available) of earlier activity:\n"
    )
    budget = SUMMARY_MAX_CHARS - len(head)
    if len(body) > budget:
        body = "…earlier entries omitted…\n" + body[-max(budget - 32, 0) :]
    return (head + body)[:SUMMARY_MAX_CHARS]


async def _summarize(
    context: ToolContext, previous: str, chunk: str, limit_chars: int
) -> tuple[str, str]:
    request = (
        ("Previous summary:\n" + previous + "\n\n" if previous else "")
        + "Messages to incorporate:\n"
        + chunk
        + f"\n\nWrite the updated summary in at most {limit_chars} characters."
    )
    reply, selection = await context.router.complete(
        Capability.BACKGROUND,
        [
            ModelMessage(role="system", content=SUMMARY_PROMPT),
            ModelMessage(role="user", content=request),
        ],
        [],
    )
    await save_usage(
        context.db,
        context.owner_id,
        context.agent_id,
        context.thread_id,
        UsageRecord(
            context.lease.run_id,
            selection.provider,
            selection.model,
            reply.usage,
            context_budget={
                **reply.provider_metadata.get("context_budget", {}),
                "purpose": "run_context_summary",
            },
        ),
    )
    text = reply.text.strip()
    if not text:
        raise LonoraError("run_summary_empty", 502)
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[: SUMMARY_MAX_CHARS - 40] + "\n…[summary truncated]"
    return text, selection.model


async def compact_context(
    context: ToolContext,
    state: dict[str, Any],
    messages: Sequence[ModelMessage],
    limits: ContextLimits,
    *,
    extra_tokens: int,
    save: Callable[[], Awaitable[None]],
) -> CompactionResult:
    """Bring the next request under the compaction threshold, if it is over it.

    Phase 1 prunes old tool results outside the protected tail. Phase 2, only if
    the request is still above the low-water mark, summarizes the middle in
    chunks, saving after each so a restart resumes instead of recomputing. Every
    boundary is a complete block.
    """
    fixed, body = _split_estimate(messages, state, limits, extra_tokens)
    trigger = body_trigger(fixed, limits)
    if body <= trigger:
        return CompactionResult()
    _, history = _split(messages)
    spans = _block_spans(history)
    if len(spans) <= TAIL_MIN_BLOCKS:
        return CompactionResult()
    tail = _tail_start(history, spans, limits)
    record = _record(state)
    if _valid_summary(record, history) is None:
        record["summary"] = None
    previous_prune = int(record.get("prune_through") or 0)
    calls = _calls(history)
    observed = observed_times(state)
    refs = cast(dict[str, Any], record.setdefault("refs", {}))
    pruned = stored = 0
    if tail > previous_prune:
        for index in range(previous_prune, tail):
            message = history[index]
            if not prunable(message):
                continue
            pruned += 1
            identifier = message.tool_call_id or ""
            call = calls.get(identifier)
            if (
                identifier in refs
                or call is None
                or len(message.content) < STORE_MIN_CHARS
                or '"result_ref"' in message.content[:4000]
            ):
                continue
            if stored >= MAX_STORES_PER_PASS:
                continue
            try:
                decoded: Any = json.loads(message.content)
            except ValueError:
                continue
            if not isinstance(decoded, dict):
                continue
            result = cast(dict[str, Any], decoded)
            try:
                pointer = await store_result(context, call, result, bounded_result(result))
                refs[identifier] = {
                    key: pointer[key]
                    for key in ("result_ref", "result_read_tool", "result_persisted")
                    if key in pointer
                }
                stored += 1
            except LonoraError as error:
                if error.code in {"stale_lease", "skill_continuation_unavailable"}:
                    raise
                refs[identifier] = {
                    "result_persisted": False,
                    "result_storage_error": error.code,
                }
        record["prune_through"] = tail
        state[STATE_KEY] = record
        await save()
    result = CompactionResult(pruned_results=pruned, stored_results=stored)
    if _split_estimate(messages, state, limits, extra_tokens)[1] <= int(trigger * LOW_WATER):
        await _report(context, record, result)
        return result
    summary: dict[str, Any] | None = _valid_summary(record, history)
    covered = int(summary["through"]) if summary else 0
    candidates = [span for span in spans if span[0] >= covered and span[1] <= tail]
    if not candidates:
        await _report(context, record, result)
        return result
    summarizer = await resolve_limits(context, Capability.BACKGROUND)
    anchor = _anchor(history)
    summarized = 0
    kind = "model"
    while candidates:
        # The previous summary travels with every chunk, so it shares the budget.
        chunk_tokens = max(
            2048,
            int(summarizer.input_tokens * CHUNK_SHARE)
            - summarizer.count(SUMMARY_PROMPT)
            - summarizer.count(str(summary["text"]) if summary else ""),
        )
        chunk: list[tuple[int, int]] = []
        size = 0
        for span in candidates:
            text = "\n".join(_excerpt(row, calls, observed) for row in history[span[0] : span[1]])
            cost = summarizer.count(text)
            if chunk and size + cost > chunk_tokens:
                break
            chunk.append(span)
            size += cost
        candidates = candidates[len(chunk) :]
        through = chunk[-1][1]
        previous = str(summary["text"]) if summary else ""
        rows = history[chunk[0][0] : through]
        try:
            text, _ = await _summarize(
                context,
                previous,
                "\n".join(_excerpt(row, calls, observed) for row in rows),
                SUMMARY_MAX_CHARS,
            )
        except Exception as error:
            if isinstance(error, LonoraError) and error.code in {
                "stale_lease",
                "skill_continuation_unavailable",
            }:
                raise
            log.warning(
                "run_summary_unavailable code=%s",
                error.code if isinstance(error, LonoraError) else type(error).__name__,
            )
            # Degrade, never fail: summarize everything left deterministically.
            through = candidates[-1][1] if candidates else through
            rows = history[chunk[0][0] : through]
            text = deterministic_summary(previous, rows, calls, observed)
            candidates = []
            kind = "deterministic"
        summarized += len(rows)
        generation = int(summary.get("generation") or 0) + 1 if summary else 1
        summary = {
            "through": through,
            "fingerprint": fingerprint(history[:through]),
            "text": text,
            "generation": generation,
            "kind": kind,
            "created_at": utcnow().isoformat(),
            "covered_messages": through,
            "kept_index": anchor if anchor is not None and anchor < through else None,
        }
        record["summary"] = summary
        state[STATE_KEY] = record
        await save()
    result = CompactionResult(
        pruned_results=pruned,
        stored_results=stored,
        summarized_messages=summarized,
        summary_kind=kind,
    )
    await _report(context, record, result)
    return result


async def _report(context: ToolContext, record: dict[str, Any], result: CompactionResult) -> None:
    if not result.changed:
        return
    summary = record.get("summary")
    await progress(
        context,
        "run.context_compacted",
        {
            "pruned_results": result.pruned_results,
            "stored_results": result.stored_results,
            "summarized_messages": result.summarized_messages,
            "summary_kind": result.summary_kind,
            "generation": cast(dict[str, Any], summary).get("generation")
            if isinstance(summary, dict)
            else None,
        },
    )
