"""The agent's optional next-reply suggestion (Q23), inside the same generation.

The model may end a conversational answer with one trailing
``<suggested_reply>…</suggested_reply>`` tag: what the owner would most likely say next.
The tag never reaches the owner as text: the stream withholds it (including an opening
tag split across provider deltas) and the final answer drops it. Only a trailing tag of
at most 60 characters becomes the suggestion; there is no extra model call and no client
default.
"""

import re

OPEN = "<suggested_reply>"
CLOSE = "</suggested_reply>"
MAX_CHARS = 60
TAG = re.compile(r"<suggested_reply>(.*?)(?:</suggested_reply>|$)", re.S)


def suggestion_stream_prefix(text: str) -> str:
    """The part of a cumulative generation that may stream: everything before the first
    opening tag, and never a trailing fragment that could still become one."""
    start = text.find(OPEN)
    if start >= 0:
        return text[:start]
    for size in range(min(len(OPEN) - 1, len(text)), 0, -1):
        if text.endswith(OPEN[:size]):
            return text[:-size]
    return text


def split_suggested_reply(text: str) -> tuple[str, str | None]:
    """The answer without any tag, and the trailing suggestion when it is valid."""
    if OPEN not in text:
        return text, None
    suggestion: str | None = None
    last = None
    for match in TAG.finditer(text):
        last = match
    if last is not None and not text[last.end() :].strip():
        candidate = " ".join(last.group(1).split())
        if candidate and len(candidate) <= MAX_CHARS:
            suggestion = candidate
    return TAG.sub("", text), suggestion
