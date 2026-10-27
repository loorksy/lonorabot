"""Admit prose without treating unbound template expressions as populated data.

Native state bindings are resolved structurally by the visual contract. Ordinary
prose has no state scope. Code spans/fences remain literal; no market value is
guessed, and ordinary braces or JSON are not templates.
"""

import re


def unbound_prose(text: str, unavailable: str, *, partial: bool = False) -> tuple[str, bool]:
    if "{{" not in text:
        return text, False
    output: list[str] = []
    fence: tuple[str, int] | None = None
    inline = 0
    missing = False
    for line in text.splitlines(keepends=True):
        block = re.match(r"^[ \t]*(`{3,}|~{3,})([^\r\n]*)", line)
        if block:
            ticks, language = block.groups()
            output.append(line)
            if fence is None:
                fence = (ticks[0], len(ticks))
            elif ticks[0] == fence[0] and len(ticks) >= fence[1] and not language.strip():
                fence = None
            continue
        if fence is not None:
            output.append(line)
            continue
        cursor = 0
        while cursor < len(line):
            if line[cursor] == "`":
                end = cursor + 1
                while end < len(line) and line[end] == "`":
                    end += 1
                count = end - cursor
                if inline == count:
                    inline = 0
                elif not inline:
                    inline = count
                output.append(line[cursor:end])
                cursor = end
                continue
            if not inline:
                if line.startswith("{{", cursor):
                    end = line.find("}}", cursor + 2)
                    if end < 0 and partial:
                        return "".join(output), missing
                    # A final malformed/incomplete reserved binding has no
                    # state scope either. Preserve line breaks and other lines;
                    # never reintroduce a dangling marker at final settlement.
                    output.append(unavailable)
                    cursor = end + 2 if end >= 0 else len(line.rstrip("\r\n"))
                    missing = True
                    continue
            output.append(line[cursor])
            cursor += 1
    return "".join(output), missing
