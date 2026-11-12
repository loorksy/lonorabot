"""Granular, atomic edits of the one versioned MEMORY document.

Operations apply in order to a working copy and the size limit is checked only
on the final result, so one batch can free room and add a fact together, and an
overflow reports the exact shortfall instead of asking for the whole document.
Adapted from Hermes Agent, NousResearch/hermes-agent revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a, tools/memory_tool.py and
tools/memory_tool_store.py: the add/patch/remove batch shape checked against
the final size, overlapping-span uniqueness and closest-line hints. Lonora keeps
its own Markdown document, its # USER.md / # MEMORY.md views, optimistic
revision and receipts instead of Hermes' delimited entry files.

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

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from lonora_core.user_error import LonoraError
from lonora_db.memory import MEMORY_CHAR_LIMIT

from .guard import DISCLOSURE_RECOVERY, disclosure_claims
from .markdown_memory import normalize_memory
from .profile import VIEW_HEADING, operating_notes

MAX_HINT_LINES = 3
HINT_LINE_CHARS = 200
# The same explicit view headings profile_documents() recognizes.
HEADING = VIEW_HEADING
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s")

# USER.md names the shared owner profile; MEMORY.md and OPERATING.md are views of
# the Agent's own document.
MemorySection = Literal["USER.md", "MEMORY.md", "OPERATING.md"]
MemoryAction = Literal["add", "patch", "remove"]


@dataclass(frozen=True)
class MemoryEdit:
    action: MemoryAction
    section: MemorySection = "MEMORY.md"
    content: str = ""
    old_text: str = ""


class MemoryEditError(LonoraError):
    """A rejected operation; nothing in the batch was applied."""

    def __init__(self, code: str, index: int, **details: Any):
        super().__init__(code, 422)
        self.index = index
        self.details = details

    def result(self) -> dict[str, Any]:
        return {"ok": False, "code": self.code, "operation_index": self.index, **self.details}


class MemoryOverflow(LonoraError):
    """The batch result exceeds the document limit; nothing was applied."""

    def __init__(
        self,
        version: int,
        current_chars: int,
        resulting_chars: int,
        limit: int = MEMORY_CHAR_LIMIT,
        document: str = "memory",
    ):
        super().__init__("memory_too_large", 413)
        self.version = version
        self.current_chars = current_chars
        self.resulting_chars = resulting_chars
        self.limit = limit
        self.document = document

    def result(self) -> dict[str, Any]:
        shortfall = self.resulting_chars - self.limit
        return {
            "ok": False,
            "code": self.code,
            "document": self.document,
            "version": self.version,
            "current_chars": self.current_chars,
            "resulting_chars": self.resulting_chars,
            "limit": self.limit,
            "shortfall": shortfall,
            "recovery": (
                f"Nothing was saved. Retry as one operations batch that also removes, "
                f"shortens or summarizes at least {shortfall} characters of stale or duplicate "
                "text in that document; the limit applies only to the batch result."
            ),
        }


def section_name(raw: str) -> MemorySection:
    if raw == "USER.md":
        return "USER.md"
    if raw == "OPERATING.md":
        return "OPERATING.md"
    return "MEMORY.md"


def headings(document: str) -> list[MemorySection]:
    return [section_name(match[1]) for match in HEADING.finditer(document)]


def occurrences(text: str, span: str) -> int:
    """Overlapping occurrences: '00' occurs twice in '1000'."""
    count, start = 0, text.find(span)
    while start >= 0:
        count += 1
        start = text.find(span, start + 1)
    return count


def closest_lines(document: str, old_text: str) -> list[str]:
    """Lines sharing most words with a stale or paraphrased old_text."""
    wanted = set(re.findall(r"\w+", old_text.casefold()))
    if not wanted:
        return []
    scored: list[tuple[float, int, str]] = []
    for index, line in enumerate(document.splitlines()):
        words = set(re.findall(r"\w+", line.casefold()))
        score = len(wanted & words) / len(wanted)
        if score >= 0.3:
            scored.append((-score, index, line.strip()[:HINT_LINE_CHARS]))
    return [line for _, _, line in sorted(scored)[:MAX_HINT_LINES]]


def _insert(before: str, entry: str, after: str) -> str:
    head = before.rstrip("\n")
    last = head.rsplit("\n", 1)[-1]
    if not head:
        separator = ""
    elif HEADING.match(last + "\n") or (LIST_ITEM.match(last) and LIST_ITEM.match(entry)):
        separator = "\n"
    else:
        separator = "\n\n"
    rest = after.lstrip("\n")
    return head + separator + entry + ("\n\n" + rest if rest else "\n")


def _add(document: str, section: MemorySection, entry: str) -> str:
    matches = list(HEADING.finditer(document))
    target = [match for match in matches if section_name(match[1]) == section]
    if target:
        following = next((m for m in matches if m.start() > target[-1].start()), None)
        end = following.start() if following else len(document)
        return _insert(document[:end], entry, document[end:])
    legacy = document[: matches[0].start()] if matches else document
    if section == "MEMORY.md" and legacy.strip():
        # Unsectioned legacy text is the MEMORY.md view; keep the fact beside it.
        return _insert(legacy, entry, document[len(legacy) :])
    return _insert(document, f"# {section}\n{entry}", "")


def _locate(document: str, old_text: str, index: int) -> int:
    count = occurrences(document, old_text)
    if count == 0:
        hint = closest_lines(document, old_text)
        raise MemoryEditError(
            "memory_edit_no_match", index, **({"closest_lines": hint} if hint else {})
        )
    if count > 1:
        raise MemoryEditError("memory_edit_ambiguous", index, matches=count)
    return document.find(old_text)


def _starts_entry(lines: list[str], index: int) -> bool:
    return (
        index == 0
        or not lines[index - 1].strip()
        or LIST_ITEM.match(lines[index]) is not None
        or MARKDOWN_HEADING.match(lines[index - 1]) is not None
    )


def _ends_entry(lines: list[str], index: int) -> bool:
    following = index + 1
    return (
        following == len(lines)
        or not lines[following].strip()
        or LIST_ITEM.match(lines[following]) is not None
        or MARKDOWN_HEADING.match(lines[following]) is not None
    )


def existing_entry(view: str, entry: str) -> str | None:
    """The stored entry exactly equal to entry, never a longer one containing it.

    Lines compare without surrounding whitespace. A one-line entry matches a whole
    line; a multi-line entry matches a whole block bounded by blank lines, list
    items or headings. 'Max daily loss 50' is therefore new beside 'Max daily loss
    500 USD', as in Hermes, which deduplicates on whole-entry equality.
    """
    wanted = [line.strip() for line in entry.split("\n")]
    lines = view.split("\n")
    stripped = [line.strip() for line in lines]
    size = len(wanted)
    for start in range(len(lines) - size + 1):
        if stripped[start : start + size] != wanted:
            continue
        if size == 1 or (_starts_entry(lines, start) and _ends_entry(lines, start + size - 1)):
            return "\n".join(stripped[start : start + size])[:HINT_LINE_CHARS]
    return None


def _line_span(document: str, start: int, old_text: str) -> tuple[int, int]:
    """The whole lines holding old_text's non-newline characters. A newline at
    either end of old_text only bounds it; it never pulls in the neighbouring line."""
    first = start + len(old_text) - len(old_text.lstrip("\n"))
    last = start + len(old_text.rstrip("\n"))
    line_start = document.rfind("\n", 0, first) + 1
    newline = document.find("\n", last)
    return line_start, len(document) if newline < 0 else newline + 1


def apply_edit(
    document: str, edit: MemoryEdit, index: int = 0, *, profile: bool = False
) -> tuple[str, dict[str, Any]]:
    """One operation on a normalized document -> (normalized result, outcome).

    ``profile`` edits the owner profile: one plain document without view headings,
    where an add appends at the end.
    """
    outcome: dict[str, Any] = {"action": edit.action}
    if edit.action == "add":
        outcome["section"] = edit.section
        entry = edit.content.replace("\r\n", "\n").strip()
        if not entry:
            raise MemoryEditError("memory_edit_content_required", index)
        if HEADING.search(entry + "\n"):
            # An entry may not open another view: text bound for MEMORY.md could
            # otherwise start a section of operating notes.
            raise MemoryEditError("memory_edit_heading_protected", index)
        if profile:
            if (duplicate := existing_entry(document, entry)) is not None:
                return document, {**outcome, "changed": False, "duplicate_of": duplicate}
            result = normalize_memory(_insert(document, entry, ""))
            return result, {**outcome, "changed": result != document}
        for name, body in _views(document):
            if name == edit.section or (edit.section == "MEMORY.md" and name is None):
                if (duplicate := existing_entry(body, entry)) is not None:
                    return document, {**outcome, "changed": False, "duplicate_of": duplicate}
        result = normalize_memory(_add(document, edit.section, entry))
        return result, {**outcome, "changed": result != document}
    old_text = edit.old_text.replace("\r\n", "\n")
    if not old_text.strip():
        raise MemoryEditError("memory_edit_old_text_required", index)
    start = _locate(document, old_text, index)
    stop = start + len(old_text)
    if edit.action == "patch":
        result = document[:start] + edit.content.replace("\r\n", "\n") + document[stop:]
    else:
        # Remove the whole lines the unique span touches, so no dangling bullet remains.
        line_start, line_stop = _line_span(document, start, old_text)
        result = re.sub(r"\n{3,}", "\n\n", document[:line_start] + document[line_stop:])
    result = normalize_memory(result)
    if headings(result) != headings(document):
        # View headings separate knowledge from operating notes; only a whole
        # document write may restructure them.
        raise MemoryEditError("memory_edit_heading_protected", index)
    return result, {**outcome, "changed": result != document}


def _views(document: str) -> list[tuple[MemorySection | None, str]]:
    matches = list(HEADING.finditer(document))
    views: list[tuple[MemorySection | None, str]] = [
        (None, document[: matches[0].start()] if matches else document)
    ]
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(document)
        views.append((section_name(match[1]), document[match.end() : end]))
    return views


def guarded_text(document: str, *, profile: bool) -> str:
    """The part of a document that later Runs follow as guidance."""
    return document if profile else operating_notes(document)


def new_disclosure_claim(before: str, after: str, *, profile: bool) -> str | None:
    """A disclosure line ``after`` adds to guided text; one already there is not new."""
    added = Counter(disclosure_claims(guarded_text(after, profile=profile)))
    added.subtract(Counter(disclosure_claims(guarded_text(before, profile=profile))))
    return next((claim for claim, count in added.items() if count > 0), None)


def disclosure_refusal(index: int, claim: str) -> "MemoryEditError":
    return MemoryEditError(
        "memory_disclosure_refused", index, statement=claim, recovery=DISCLOSURE_RECOVERY
    )


def apply_edits(
    document: str,
    edits: list[MemoryEdit],
    version: int,
    *,
    profile: bool = False,
    limit: int = MEMORY_CHAR_LIMIT,
) -> tuple[str, list[dict[str, Any]]]:
    """All operations or none; the limit is checked on the final document only.

    A batch that changes nothing returns the stored document itself, so the
    caller keeps the current revision instead of committing an identical one.
    An operation that adds a disclosure line to the method (or to the
    owner profile) rejects the whole batch.
    """
    original = normalize_memory(document)
    current = original
    applied: list[dict[str, Any]] = []
    for index, edit in enumerate(edits):
        current, outcome = apply_edit(current, edit, index, profile=profile)
        if claim := new_disclosure_claim(original, current, profile=profile):
            raise disclosure_refusal(index, claim)
        applied.append(outcome)
    if current == original:
        return document, applied
    if len(current) > limit:
        raise MemoryOverflow(
            version,
            len(document),
            len(current),
            limit,
            "owner_profile" if profile else "memory",
        )
    return current, applied
