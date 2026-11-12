"""Compile optional native composition within the existing model generation.

This is a bounded presentation compiler, not an intent/presentation router. Only
the model emits the marker. Tool evidence is resolved from this request, and
resource references use the existing owned database rows.
"""

import json
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.genui import CardError, parse_lines
from lonora_contracts.visual_response import RichContent
from lonora_core.public_reply import redact_private_reply
from lonora_db.genui_submit import account_label, enabled_accounts
from lonora_db.schema import AgentRow
from lonora_tools.context import ToolContext
from sqlalchemy.exc import SQLAlchemyError

from .context.financial_result import public_broker_ids
from .display_bindings import unbound_prose
from .genui_capabilities import UiCapabilities, capabilities
from .genui_compile import AgentScope, compile_card

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
        "For a card fact use its call_id exactly as listed, not the tool name. "
        "JSON Pointer paths refer to that call's actual returned JSON. This list "
        "does not require a visual; plain prose remains valid.\n"
        + json.dumps(references, separators=(",", ":"))
        + "\n</lonora_visual_observations>"
    )


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

    def card(self, document: dict[str, Any], *, building: bool = False) -> None:
        """A v2 card: its text alternative is the model's fallback (``content`` = lead +
        blank line + fallback); a building card projects no text until it is complete."""
        part: dict[str, Any] = {"type": "ui", "document": document}
        if building:
            part["building"] = True
        self.segments.append((part, "" if building else "\n" + document["fallback"] + "\n"))

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
            # A building v2 card projects no text: it shows once everything before it has.
            if remaining < 0 or (remaining == 0 and not (part["type"] == "ui" and not projected)):
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


# A building card before its head line is complete (GENUI_PLAN §9.1).
SKELETON: dict[str, Any] = {
    "v": 2,
    "kind": "form",
    "title": "",
    "facts": {},
    "state": {},
    "calc": {},
    "blocks": [],
    "fallback": "",
}


class VisualReplyProjector:
    """Compile complete frames once, while independent prose keeps flowing.

    A prefix never synthesizes a missing property, state or partial component.
    Incomplete frames wait for their closing line; earlier validated frames and
    following ordinary prose do not wait for the complete model generation.
    """

    def __init__(self, context: ToolContext, messages: list[ModelMessage]):
        self.context, self.messages = context, messages
        self.public_ids = public_broker_ids(messages)
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
        self.capabilities: UiCapabilities = capabilities(
            language="ar" if re.search(r"[\u0620-\u064a]", owner) or not owner else "en"
        )
        self.scope: AgentScope | None = None
        self.cards: dict[str, dict[str, Any] | None] = {}

    async def agent_scope(self) -> AgentScope:
        """The card's agent: its id and, for a fixed-market agent, its bound pair."""
        if self.scope is None:
            scope = AgentScope(agent_id=self.context.agent_id)
            async with self.context.db.sessions() as session:
                agent = await session.get(AgentRow, self.context.agent_id)
                if agent is not None:
                    scope.bound_account = agent.trading_account_id
                    scope.bound_symbol = agent.trading_symbol
                    accounts = await enabled_accounts(session, self.context.owner_id)
                    scope.several_accounts = len(accounts) > 1
                    if scope.several_accounts:
                        # The card's account is one this request read: name each directly,
                        # owner-checked, wherever it sits among the owner's accounts.
                        read = {
                            str(call.arguments["account_id"])
                            for message in self.messages
                            for call in message.tool_calls or []
                            if isinstance(call.arguments.get("account_id"), str)
                        }
                        if agent.trading_account_id:
                            read.add(agent.trading_account_id)
                        scope.named_accounts = frozenset(
                            [
                                account
                                for account in read
                                if await account_label(session, account, self.context.owner_id)
                            ]
                        )
            self.scope = scope
        return self.scope

    async def _v2(self, result: VisualProjection, raw: str, *, partial: bool, closed: bool) -> bool:
        """Compile a v2 card. Returns False when a streaming card is not shown yet."""
        final = closed or not partial
        key = ("F" if final else "P") + raw
        if key not in self.cards:
            try:
                card = parse_lines(raw, final=final)
            except (CardError, RecursionError, MemoryError) as error:
                if final:
                    code = str(error) if isinstance(error, CardError) else "card_fallback"
                    self.diagnostics.append({"code": code, "frame": 0, "paths": []})
                self.cards[key] = None
                card = None
            if card is not None:
                try:
                    scope = await self.agent_scope()
                    self.cards[key] = compile_card(
                        card, self.messages, scope, self.capabilities, self.public_ids, final=final
                    )
                    if final:
                        self.diagnostics.extend(card.diagnostics.items[:24])
                except (
                    CardError,
                    ValueError,
                    TypeError,
                    KeyError,
                    RecursionError,
                    OverflowError,
                    MemoryError,
                    SQLAlchemyError,
                ) as error:
                    code = str(error) if isinstance(error, CardError) else "card_fallback"
                    if final:
                        self.diagnostics.extend(card.diagnostics.items[:24])
                        self.diagnostics.append({"code": code, "frame": 0, "paths": []})
                    self.cards[key] = None
                    if final:
                        self.cards["fallback:" + key] = {"fallback": card.fallback}
        document = self.cards[key]
        if document is None:
            if not final:
                # Until the head line is complete: the skeleton, never nothing (review).
                result.card(dict(SKELETON), building=True)
                return False
            fallback = (self.cards.get("fallback:" + key) or {}).get("fallback")
            result.errors.append("visual_frame_rejected")
            text = fallback or self.failure
            self._prose(
                result, "\n" + redact_private_reply(text, public_ids=self.public_ids) + "\n"
            )
            return True
        result.card(document, building=not final)
        return final

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
        cards = 0
        for index in range(12):
            match = visual_start(text, position)
            if not match:
                break
            result.saw_visual = True
            self._prose(result, text[position : match.start()])
            closing = END.search(text, match.end())
            body = text[match.end() : closing.start() if closing else len(text)]
            complete = closing is not None and text[: closing.end()].endswith("\n")
            if cards:
                # One card per reply, even when the first fell back: a second is dropped,
                # its fallback kept as text (review).
                if partial and not complete:
                    return result
                self.diagnostics.append({"code": "interface_extra", "frame": index})
                try:
                    extra = parse_lines(body, final=True).fallback
                except CardError:
                    extra = None
                if extra:
                    self._prose(result, "\n" + extra + "\n")
                position = closing.end() if closing else len(text)
                continue
            cards += 1
            if partial and not complete:
                await self._v2(result, body, partial=True, closed=False)
                return result
            await self._v2(result, body, partial=partial, closed=True)
            position = closing.end() if closing else len(text)
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
