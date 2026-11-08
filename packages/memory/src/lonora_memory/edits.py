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
from dataclasses import dataclass
from typing import Any, Literal

from lonora_core.user_error import LonoraError
from lonora_db.memory import MEMORY_CHAR_LIMIT

from .markdown_memory import normalize_memory

MAX_HINT_LINES = 3
HINT_LINE_CHARS = 200
# The same explicit view headings profile_documents() recognizes.
HEADING = re.compile(r"(?m)^# (USER\.md|(?:memory/)?MEMORY\.md)[ \t]*\n")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")

MemorySection = Literal["USER.md", "MEMORY.md"]
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

    def __init__(self, version: int, current_chars: int, resulting_chars: int):
        super().__init__("memory_too_large", 413)
        self.version = version
        self.current_chars = current_chars
        self.resulting_chars = resulting_chars

    def result(self) -> dict[str, Any]:
        shortfall = self.resulting_chars - MEMORY_CHAR_LIMIT
        return {
            "ok": False,
            "code": self.code,
            "version": self.version,
            "current_chars": self.current_chars,
            "resulting_chars": self.resulting_chars,
            "limit": MEMORY_CHAR_LIMIT,
            "shortfall": shortfall,
            "recovery": (
                f"Nothing was saved. Retry as one operations batch that also removes or "
                f"shortens at least {shortfall} characters of stale or duplicate memory; the "
                "limit applies only to the batch result."
            ),
        }


def section_name(raw: str) -> MemorySection:
    return "USER.md" if raw == "USER.md" else "MEMORY.md"


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


def apply_edit(document: str, edit: MemoryEdit, index: int = 0) -> tuple[str, bool]:
    """One operation on a normalized document -> (result, changed)."""
    if edit.action == "add":
        entry = edit.content.replace("\r\n", "\n").strip()
        if not entry:
            raise MemoryEditError("memory_edit_content_required", index)
        view = "\n".join(
            body
            for name, body in _views(document)
            if name == edit.section or (edit.section == "MEMORY.md" and name is None)
        )
        if entry in view:
            return document, False
        return _add(document, edit.section, entry), True
    old_text = edit.old_text.replace("\r\n", "\n")
    if not old_text.strip():
        raise MemoryEditError("memory_edit_old_text_required", index)
    start = _locate(document, old_text, index)
    stop = start + len(old_text)
    if edit.action == "patch":
        result = document[:start] + edit.content.replace("\r\n", "\n") + document[stop:]
    else:
        # Remove the whole lines the unique span touches, so no dangling bullet remains.
        line_start = document.rfind("\n", 0, start) + 1
        if old_text.endswith("\n"):
            line_stop = stop
        else:
            newline = document.find("\n", stop)
            line_stop = len(document) if newline < 0 else newline + 1
        result = re.sub(r"\n{3,}", "\n\n", document[:line_start] + document[line_stop:])
    if headings(result) != headings(document):
        # View headings separate owner preferences from knowledge; only a whole
        # document write may restructure them.
        raise MemoryEditError("memory_edit_heading_protected", index)
    return result, result != document


def _views(document: str) -> list[tuple[MemorySection | None, str]]:
    matches = list(HEADING.finditer(document))
    views: list[tuple[MemorySection | None, str]] = [
        (None, document[: matches[0].start()] if matches else document)
    ]
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(document)
        views.append((section_name(match[1]), document[match.end() : end]))
    return views


def apply_edits(
    document: str, edits: list[MemoryEdit], version: int
) -> tuple[str, list[dict[str, Any]]]:
    """All operations or none; the limit is checked on the final document only."""
    current = normalize_memory(document)
    applied: list[dict[str, Any]] = []
    for index, edit in enumerate(edits):
        current, changed = apply_edit(current, edit, index)
        current = normalize_memory(current)
        applied.append(
            {
                "action": edit.action,
                **({"section": edit.section} if edit.action == "add" else {}),
                "changed": changed,
            }
        )
    if len(current) > MEMORY_CHAR_LIMIT:
        raise MemoryOverflow(version, len(document), len(current))
    return current, applied
