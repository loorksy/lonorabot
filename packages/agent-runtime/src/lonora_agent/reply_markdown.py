"""Repair bold markers a model wrote with a space inside them.

CommonMark does not open emphasis on ``** text**`` or close it on ``**text **``, so the
owner sees the raw asterisks. The spaces move outside the markers. Code spans, fenced
blocks and valid Markdown are left exactly as written.
"""

import re

_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
_CODE = re.compile(r"(`+)(?:.+?)\1")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _repair(match: re.Match[str]) -> str:
    inner = match[1]
    text = inner.strip()
    if not text or text == inner:
        return match[0]
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    return lead + "**" + text + "**" + trail


def _line(line: str) -> str:
    parts: list[str] = []
    position = 0
    for code in _CODE.finditer(line):
        parts.append(_BOLD.sub(_repair, line[position : code.start()]))
        parts.append(code[0])
        position = code.end()
    parts.append(_BOLD.sub(_repair, line[position:]))
    return "".join(parts)


def normalize_bold(text: str) -> str:
    if "**" not in text:
        return text
    fenced = False
    lines: list[str] = []
    for line in text.split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
        lines.append(line if fenced or _FENCE.match(line) else _line(line))
    return "\n".join(lines)
