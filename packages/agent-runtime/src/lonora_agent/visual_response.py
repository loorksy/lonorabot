"""Compile optional native composition within the existing model generation.

This is a bounded presentation compiler, not an intent/presentation router. Only
the model emits the marker. Tool evidence is resolved from this request, and
resource references use the existing owned database rows.
"""

import json
import logging
import math
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.visual_response import MAX_VISUAL_BYTES, RichContent, VisualDocument
from lonora_contracts.visual_values import EXTENDED_ARITY, evaluate_extended_visual_op
from lonora_core.public_reply import public_reply_violation, redact_private_reply
from lonora_db.schema import ArtifactRow, CloudChartRow
from lonora_tools.context import ToolContext
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .context.financial_result import public_broker_ids
from .display_bindings import unbound_prose

START = re.compile(r"^[ \t]*(?:`{3,}|~{3,})[ \t]*lonora-ui\b[^\n]*\n?", re.M | re.I)
END = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:\r?\n|$)")
PRIVATE_KEY = re.compile(
    r"password|secret|token|credential|private.?key|authorization|api.?key|access.?key|signing.?key|recovery.?code",
    re.I,
)
FAILED = {"error", "failed", "denied", "unavailable", "rejected"}


def visual_start(text: str, position: int = 0) -> re.Match[str] | None:
    """Find protocol frames outside ordinary Markdown code examples."""
    fence: tuple[str, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^[ \t]*(`{3,}|~{3,})([^\r\n]*)", line)
        if marker:
            ticks, language = marker.groups()
            if fence is not None:
                if ticks[0] == fence[0] and len(ticks) >= fence[1] and not language.strip():
                    fence = None
            else:
                native = START.match(text, offset)
                if native is not None and offset >= position:
                    return native
                fence = (ticks[0], len(ticks))
        offset += len(line)
    return None


def visual_stream_prefix(text: str) -> str:
    """Withhold the first visual fence, including its split provider tokens.

    Following text waits for the atomic validated composition too, so mixed
    ordering cannot change between provisional streaming and durable publication.
    """
    match = visual_start(text)
    if match:
        return text[: match.start()]
    last_line = text.rsplit("\n", 1)[-1]
    token = last_line.lstrip(" \t")
    opening = re.fullmatch(r"(?:`+|~+)[ \t]*([^`~\n]*)", token)
    if opening and "lonora-ui".startswith(opening[1].lower()):
        return text[: len(text) - len(last_line)]
    return text


def _evidence(messages: list[ModelMessage]) -> dict[str, tuple[str, Any]]:
    boundary = max(
        (
            i
            for i, m in enumerate(messages)
            if m.role == "user" and m.context_origin == "conversation"
        ),
        default=-1,
    )
    current = messages[boundary + 1 :]
    calls = {call.id: call.name for m in current if m.role == "assistant" for call in m.tool_calls}
    evidence: dict[str, tuple[str, Any]] = {}
    for message in current:
        identity = message.tool_call_id
        if message.role != "tool" or identity not in calls:
            continue
        try:
            raw = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        evidence[identity] = (calls[identity], raw)
    return evidence


def visual_observation_catalog(messages: list[ModelMessage]) -> str:
    """Expose transport call identities to the model, without duplicating data.

    Provider tool-use IDs are not necessarily visible as tokens in their result
    content. This current-request projection makes exact evidence addressable;
    it neither selects presentation nor reads any new data or invokes a model.
    """
    references = [
        {"call_id": identity, "tool": name}
        for identity, (name, result) in _evidence(messages).items()
        if len(identity) <= 200
        and not (
            isinstance(result, dict)
            and (
                cast(dict[str, Any], result).get("ok") is False
                or cast(dict[str, Any], result).get("error")
                or str(cast(dict[str, Any], result).get("status", "")).lower() in FAILED
            )
        )
    ][-24:]
    if not references:
        return ""
    return (
        "<lonora_visual_observations>\n"
        "Actual current-request evidence identities (metadata, never user-facing). "
        "For an observed visual use fact.call_id exactly as listed, not the tool name. "
        "JSON Pointer paths refer to that call's actual returned JSON. This list "
        "does not require a visual; plain prose remains valid.\n"
        + json.dumps(references, separators=(",", ":"))
        + "\n</lonora_visual_observations>"
    )


def _pointer(data: Any, path: str) -> tuple[Any, str | None]:
    timestamp = None
    for token in [*path.split("/")[1:], None]:
        if isinstance(data, dict):
            data = cast(dict[str, Any], data)
            if (
                data.get("ok") is False
                or data.get("error")
                or str(data.get("status", "")).lower() in FAILED
            ):
                raise ValueError("visual_evidence_failed")
            for key in ("observed_at", "timestamp", "updated_at", "as_of"):
                if isinstance(data.get(key), str):
                    timestamp = str(data[key])[:80]
                    break
        if token is None:
            break
        key = token.replace("~1", "/").replace("~0", "~")
        if PRIVATE_KEY.search(key):
            raise ValueError("visual_evidence_private")
        if isinstance(data, dict) and key in data:
            data = cast(dict[str, Any], data)[key]
        elif isinstance(data, list) and key.isdigit() and int(key) < len(cast(list[Any], data)):
            data = cast(list[Any], data)[int(key)]
        elif isinstance(data, list) and key == "length":
            data = len(cast(list[Any], data))
        else:
            raise ValueError("visual_evidence_path_unknown")
    if not (data is None or isinstance(data, str | int | float | bool)):
        raise ValueError("visual_evidence_not_scalar")
    if isinstance(data, float) and not math.isfinite(data):
        raise ValueError("visual_evidence_not_finite")
    return data, timestamp


def _derived(value: Any) -> bool:
    if isinstance(value, dict):
        value = cast(dict[str, Any], value)
        if set(value) == {"source"}:
            return True
        if "op" in value:
            return any(_derived(arg) for arg in value.get("args", []))
    return False


def _observed(node: dict[str, Any]) -> None:
    values: list[Any] = []
    if node["type"] in {"metric", "progress"}:
        values.append(node.get("value"))
    if node["type"] == "table":
        values.extend(value for row in node.get("rows", []) for value in row.values())
    if node["type"] == "chart":
        values.extend(value for point in node.get("points", []) for value in point.values())
    if any(value is not None and not _derived(value) for value in values):
        raise ValueError("visual_observation_requires_evidence")
    for child in node.get("children", []):
        _observed(child)


async def _resources(context: ToolContext, node: dict[str, Any]) -> None:
    references: list[tuple[str, str, bool]] = []

    def collect(item: dict[str, Any]) -> None:
        if item["type"] == "image":
            references.append(("artifact", item["artifact_id"], True))
        action = item.get("action")
        if action and action["kind"] in {"open_chart", "open_artifact"}:
            kind = "chart" if action["kind"] == "open_chart" else "artifact"
            references.append((kind, action["resource_id"], False))
        for child in item.get("children", []):
            collect(child)

    collect(node)
    if not references:
        return
    async with context.db.sessions() as session:
        for kind, identity, image in set(references):
            model = CloudChartRow if kind == "chart" else ArtifactRow
            row = await session.get(model, identity)
            if (
                row is None
                or row.owner_id != context.owner_id
                or row.agent_id != context.agent_id
                or row.thread_id != context.thread_id
                or row.state.get("internal_tool_result")
                or (image and not str(row.payload.get("media_type", "")).startswith("image/"))
            ):
                raise ValueError("visual_resource_not_available")


async def compile_document(
    context: ToolContext, raw: Any, messages: list[ModelMessage]
) -> dict[str, Any]:
    if not isinstance(raw, dict) or "facts" in raw:
        raise ValueError("visual_untrusted_facts")
    document = VisualDocument.model_validate(raw).model_dump(mode="json", exclude_unset=True)
    document["version"] = 1
    evidence = _evidence(messages)
    facts: dict[str, Any] = {}
    resolved: dict[tuple[str, str], str] = {}
    unavailable: set[tuple[str, str]] = set()
    public_ids = public_broker_ids(messages)

    def transform(value: Any) -> Any:
        if isinstance(value, list):
            return [transform(item) for item in cast(list[Any], value)]
        if not isinstance(value, dict):
            return value
        value = cast(dict[str, Any], value)
        if set(value) == {"source"}:
            raise ValueError("visual_untrusted_source")
        if set(value) == {"fact"}:
            call_id, path = value["fact"]["call_id"], value["fact"]["path"]
            identity = (call_id, path)
            if identity in unavailable:
                return None
            if identity not in resolved:
                try:
                    if call_id not in evidence:
                        raise ValueError("visual_evidence_unknown")
                    source, result = evidence[call_id]
                    scalar, timestamp = _pointer(result, path)
                except ValueError as error:
                    if str(error) not in {
                        "visual_evidence_unknown",
                        "visual_evidence_path_unknown",
                    }:
                        raise
                    # Missing observations have no value or trusted provenance.
                    # Keep independently verified cells in an otherwise valid
                    # document; never guess a replacement call, path or value.
                    unavailable.add(identity)
                    return None
                key = "f" + str(len(facts))
                if isinstance(scalar, str):
                    scalar = redact_private_reply(scalar, public_ids=public_ids)
                facts[key] = {
                    "value": scalar,
                    "source": source,
                    "observed_at": redact_private_reply(timestamp, public_ids=public_ids)
                    if timestamp is not None
                    else None,
                }
                resolved[identity] = key
            return {"source": resolved[identity]}
        result = {key: transform(item) for key, item in value.items()}
        # Only display strings are scrubbed. Trusted resource identities remain
        # metadata and must survive the same authorized open/read path.
        for key in ("text", "label"):
            if isinstance(result.get(key), str):
                result[key] = redact_private_reply(result[key], public_ids=public_ids)
        for key in ("value", "unit"):
            if isinstance(result.get(key), str):
                result[key] = redact_private_reply(result[key], public_ids=public_ids)
        for key in ("rows", "points"):
            if isinstance(result.get(key), list):
                result[key] = [
                    {
                        field: redact_private_reply(cell, public_ids=public_ids)
                        if isinstance(cell, str)
                        else cell
                        for field, cell in row.items()
                    }
                    for row in result[key]
                ]
        return result

    document = transform(document)
    if unavailable and not any(fact["value"] is not None for fact in facts.values()):
        raise ValueError("visual_evidence_unavailable")
    if unavailable:
        logging.getLogger(__name__).warning(
            "visual_evidence_partial", extra={"unavailable_fact_count": len(unavailable)}
        )
    document["state"] = {
        key: redact_private_reply(value, public_ids=public_ids) if isinstance(value, str) else value
        for key, value in document.get("state", {}).items()
    }
    document["facts"] = facts
    _guard_composed_display(document, public_ids)
    if document["mode"] == "observed":
        _observed(document["root"])
    await _resources(context, document["root"])
    return VisualDocument.model_validate(document).model_dump(mode="json", exclude_unset=True)


def _guard_composed_display(document: dict[str, Any], public_ids: set[str]) -> None:
    """Check expressions too: split literals must not bypass display privacy.

    Inspect every branch, including currently hidden nodes. Direct display
    strings are already scrubbed above; a sensitive newly composed expression
    rejects its frame before either the compatibility text or rich tree leaves.
    Local subsequent state edits also use the shared evaluator's privacy check.
    """

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in cast(list[Any], value):
                walk(item)
        elif isinstance(value, dict):
            value = cast(dict[str, Any], value)
            if value.get("op") == "concat":
                args = [_evaluate(arg, document) for arg in value.get("args", [])]
                if all(isinstance(arg, str | int | float | bool) for arg in args):
                    composed = "".join(str(arg) for arg in args)
                    if "{{" in composed:
                        raise ValueError("visual_display_binding_unresolved")
                    if public_reply_violation(composed, public_ids=public_ids):
                        raise ValueError("visual_composed_display_private")
            for item in value.values():
                walk(item)

    walk(document["root"])
    if public_reply_violation(text_projection(document), public_ids=public_ids):
        raise ValueError("visual_composed_display_private")


def _evaluate(value: Any, document: dict[str, Any]) -> Any:
    """Text compatibility uses the same scalar semantics as the native evaluator."""
    if not isinstance(value, dict):
        return value
    value = cast(dict[str, Any], value)
    if "source" in value:
        return document.get("facts", {}).get(value["source"], {}).get("value")
    if "state" in value:
        return document.get("state", {}).get(value["state"])
    op = value.get("op")
    try:
        if op == "if":
            condition, positive, negative = value["args"]
            return _evaluate(positive if _evaluate(condition, document) else negative, document)
        args = [_evaluate(arg, document) for arg in value.get("args", [])]
        if op in EXTENDED_ARITY:
            return evaluate_extended_visual_op(op, args)
        if op == "eq":
            # JavaScript strict equality considers int/float the same numeric
            # type, but never treats a boolean as the number zero or one.
            same_type = type(args[0]) is type(args[1]) or all(
                isinstance(arg, int | float) and not isinstance(arg, bool) for arg in args
            )
            return same_type and args[0] == args[1]
        if op in {"and", "or", "not"}:
            return all(args) if op == "and" else any(args) if op == "or" else not args[0]
        if any(isinstance(arg, bool) or not isinstance(arg, int | float) for arg in args):
            return None
        result: Any = None
        if op in {"gt", "gte", "lt", "lte"}:
            result = {
                "gt": lambda: args[0] > args[1],
                "gte": lambda: args[0] >= args[1],
                "lt": lambda: args[0] < args[1],
                "lte": lambda: args[0] <= args[1],
            }[op]()
        elif op == "add":
            result = sum(args)
        elif op == "mul":
            result = math.prod(args)
        elif op == "sub":
            result = args[0] - args[1]
        elif op == "div":
            result = args[0] / args[1] if args[1] else None
        elif op == "round":
            places = args[1] if len(args) == 2 else 0
            if int(places) != places or not 0 <= places <= 8:
                return None
            precision = 10 ** int(places)
            result = math.floor((args[0] + 2.220446049250313e-16) * precision + 0.5) / precision
        elif op == "abs":
            result = abs(args[0])
        elif op in {"min", "max"}:
            result = min(args) if op == "min" else max(args)
        if isinstance(result, int | float) and not math.isfinite(result):
            return None
        return result
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def text_projection(document: dict[str, Any]) -> str:
    lines: list[str] = []

    def display(value: Any) -> str:
        actual = _evaluate(value, document)
        if actual is None or (isinstance(actual, float) and not math.isfinite(actual)):
            return "—"
        return str(actual)

    def walk(node: dict[str, Any]) -> None:
        if not _evaluate(node.get("visible", True), document):
            return
        label = node.get("text") or node.get("label") or ""
        if "value" in node:
            label = (label + ": " if label else "") + display(node["value"])
            if node.get("unit") is not None:
                label += " " + display(node["unit"])
        if label:
            lines.append(label)
        if node.get("state_key"):
            lines.append(display({"state": node["state_key"]}))
        for row in node.get("rows", []):
            lines.append(" | ".join(display(value) for value in row.values()))
        for point in node.get("points", []):
            lines.append(display(point["label"]) + ": " + display(point["value"]))
        for vertex in node.get("vertices", []):
            lines.append(vertex["label"])
        for child in node.get("children", []):
            walk(child)

    if document["mode"] in {"example", "estimate"}:
        lines.append("[" + document["mode"] + "]")
    walk(document["root"])
    return "\n".join(lines)[:18000]


def read_frame(raw: str) -> Any:
    """Recover only terminal container closers in a finished fence.

    Some providers omit or transpose the last braces of complete JSON. This adds no
    key, value, quotation or action; all resulting data still passes the exact
    same evidence, resource and native-contract checks. Truncated strings,
    interior mismatches and nonterminal syntax errors remain invalid.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        end = len(raw.rstrip("}] \t\r\n"))
        if error.pos < end:
            raise
    stack: list[str] = []
    quoted = escaped = False
    prefix = raw[:end]
    for character in prefix:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "{[":
            stack.append("}" if character == "{" else "]")
            if len(stack) > 24:
                raise ValueError("visual_json_too_deep")
        elif character in "}]":
            if not stack or stack.pop() != character:
                raise ValueError("visual_json_mismatch")
    if quoted or not stack:
        raise ValueError("visual_json_incomplete")
    return json.loads(prefix + "".join(reversed(stack)))


class VisualProjection:
    """An ordered safe projection; offsets also bound the legacy text stream."""

    def __init__(self) -> None:
        self.segments: list[tuple[dict[str, Any], str]] = []
        self.errors: list[str] = []
        self.saw_visual = False
        self.privacy_redacted = False

    @property
    def text(self) -> str:
        return "".join(text for _, text in self.segments)

    def prose(self, text: str) -> None:
        if text:
            self.segments.append(({"type": "text", "text": text}, text))

    def visual(self, document: dict[str, Any]) -> None:
        # Preserve all original prose whitespace. Replacing just the internal
        # frame makes the progressively admitted prefix equal the final message.
        self.segments.append(
            ({"type": "ui", "document": document}, text_projection(document) + "\n")
        )

    def visual_boundaries(self) -> list[int]:
        end = 0
        boundaries: list[int] = []
        for part, projected in self.segments:
            end += len(projected)
            if part["type"] == "ui":
                boundaries.append(end)
        return boundaries

    def rich_until(self, limit: int | None = None) -> dict[str, Any] | None:
        if not self.saw_visual:
            return None
        remaining = len(self.text) if limit is None else limit
        parts: list[dict[str, Any]] = []
        for part, projected in self.segments:
            if remaining <= 0:
                break
            if part["type"] == "ui":
                if remaining < len(projected):
                    break
                parts.append(part)
            else:
                visible = projected[:remaining].strip("\r\n")
                if visible.strip():
                    if parts and parts[-1]["type"] == "text":
                        parts[-1] = {"type": "text", "text": parts[-1]["text"] + "\n" + visible}
                    else:
                        parts.append({"type": "text", "text": visible})
            remaining -= len(projected)
        if not parts:
            return None
        try:
            return RichContent.model_validate({"version": 1, "parts": parts}).model_dump(
                mode="json", exclude_unset=True
            )
        except (ValueError, TypeError, RecursionError):
            if "visual_response_rejected" not in self.errors:
                self.errors.append("visual_response_rejected")
            return None


class VisualReplyProjector:
    """Compile complete frames once, while independent prose keeps flowing.

    A prefix never synthesizes a missing property, state or partial component.
    Incomplete frames wait for their closing line; earlier validated frames and
    following ordinary prose do not wait for the complete model generation.
    """

    def __init__(self, context: ToolContext, messages: list[ModelMessage]):
        self.context, self.messages = context, messages
        self.public_ids = public_broker_ids(messages)
        self.cache: dict[tuple[int, str], dict[str, Any] | None] = {}
        self.diagnostics: list[dict[str, Any]] = []
        owner = next(
            (
                m.content
                for m in reversed(messages)
                if m.role == "user" and m.context_origin == "conversation"
            ),
            "",
        )
        self.failure = (
            "تعذر عرض هذا الجزء التفاعلي."
            if re.search(r"[\u0620-\u064a]", owner)
            else "This interactive section could not be displayed."
        )
        self.unavailable = "غير متاح" if re.search(r"[\u0620-\u064a]", owner) else "Unavailable"
        self.missing_binding_logged = False

    def _failure(self, error: Exception, index: int) -> None:
        # Never log Pydantic inputs, model output, resource IDs or exception
        # strings. Codes and structural locations suffice to replay a failure.
        code = "visual_frame_rejected"
        paths: list[str] = []
        if isinstance(error, ValidationError):
            known = {
                "root",
                "children",
                "value",
                "label",
                "text",
                "state",
                "action",
                "args",
                "type",
                "id",
                "version",
                "mode",
                "fields",
                "rows",
                "points",
                "options",
                "state_key",
                "fact",
                "path",
                "call_id",
            }
            for item in error.errors(include_input=False)[:8]:
                structural = item.get("ctx", {}).get("visual_path")
                # The contract builds these locations from fixed field names
                # and numeric positions, never from user-defined state/row keys.
                if isinstance(structural, str) and re.fullmatch(
                    r"(?:root|value)(?:\.(?:children|value|unit|visible|args|rows|cells|points|label|[0-9]+))*",
                    structural,
                ):
                    paths.append(structural)
                else:
                    paths.append(
                        ".".join(
                            str(p) if isinstance(p, int) or p in known else "field"
                            for p in item["loc"]
                        )
                        or "document"
                    )
            code = "visual_schema_invalid"
        elif (
            error.args
            and isinstance(error.args[0], str)
            and re.fullmatch(r"visual_[a-z_]+", error.args[0])
        ):
            code = error.args[0]
        diagnostic = {"frame": index, "code": code, "paths": paths}
        if isinstance(error, json.JSONDecodeError):
            diagnostic.update({"line": error.lineno, "column": error.colno})
        self.diagnostics.append(diagnostic)
        logging.getLogger(__name__).warning(
            "visual_frame_rejected", extra={"visual_diagnostic": diagnostic}
        )

    def _prose(self, result: VisualProjection, text: str, *, partial: bool = False) -> None:
        protected = redact_private_reply(text, public_ids=self.public_ids)
        result.privacy_redacted |= text != protected
        protected, missing = unbound_prose(protected, self.unavailable, partial=partial)
        if missing:
            result.errors.append("visual_unresolved_text_binding")
            if not self.missing_binding_logged:
                self.diagnostics.append(
                    {"code": "visual_unresolved_text_binding", "paths": ["prose"]}
                )
                self.missing_binding_logged = True
        result.prose(protected)

    async def project(self, text: str, *, partial: bool = False) -> VisualProjection:
        result = VisualProjection()
        position = 0
        for index in range(12):
            match = visual_start(text, position)
            if not match:
                break
            result.saw_visual = True
            self._prose(result, text[position : match.start()])
            closing = END.search(text, match.end())
            # A closing line at the provider's current EOF is still ambiguous:
            # its next chunk may extend the line. Final EOF itself is complete.
            if partial and (closing is None or not text[: closing.end()].endswith("\n")):
                return result
            position = closing.end() if closing else len(text)
            raw = text[match.end() : closing.start() if closing else len(text)]
            identity = (match.start(), raw)
            if identity not in self.cache:
                try:
                    if closing is None or len(raw.encode()) > MAX_VISUAL_BYTES:
                        raise ValueError("visual_frame_invalid")
                    self.cache[identity] = await compile_document(
                        self.context, read_frame(raw), self.messages
                    )
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    RecursionError,
                    OverflowError,
                    SQLAlchemyError,
                ) as error:
                    self._failure(error, index)
                    self.cache[identity] = None
            document = self.cache[identity]
            if document is None:
                result.errors.append("visual_frame_rejected")
                result.prose(self.failure + "\n")
            else:
                if not partial:
                    try:
                        await _resources(self.context, document["root"])
                    except (ValueError, SQLAlchemyError) as error:
                        self._failure(error, index)
                        result.errors.append("visual_frame_rejected")
                        result.prose(self.failure + "\n")
                        continue
                result.visual(document)
        tail = text[position:]
        excess = visual_start(tail)
        if excess:
            tail = tail[: excess.start()]
            result.errors.append("visual_parts_exceeded")
        if partial:
            tail = visual_stream_prefix(tail)
        self._prose(result, tail, partial=partial)
        return result


async def parse_visual_reply(
    context: ToolContext, text: str, messages: list[ModelMessage]
) -> tuple[str, dict[str, Any] | None, list[str]]:
    if not visual_start(text) and "{{" not in text:
        return text, None, []
    result = await VisualReplyProjector(context, messages).project(text)
    return result.text, result.rich_until(), result.errors
