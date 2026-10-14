"""Bounded provider diagnostics without credentials, URLs or opaque identifiers."""

import re
from collections.abc import Iterable


def safe_exception_message(error: BaseException, secrets: Iterable[str] = ()) -> str:
    message = str(error)
    candidate: BaseException | None = error
    for _ in range(4):
        if candidate is None:
            break
        diagnostic = getattr(candidate, "diagnostic_message", None)
        if isinstance(diagnostic, str):
            message = diagnostic
            break
        candidate = candidate.__cause__
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"(?i)\b(?:https?|wss?)://[^\s<>\"']+", "[redacted-url]", message)
    message = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s,;\"']+", r"\1 [redacted]", message)
    message = re.sub(
        r"(?i)(\b(?:authorization|password|secret|token|api[-_]?key|auth[-_]?token|username)[\"']?\s*[:=]\s*)(?:[\"'][^\"'\r\n]*[\"']|[^\s,;}]+)",
        r"\1[redacted]",
        message,
    )
    message = re.sub(
        r"(?i)(\b(?:password|secret|token)\s+)(?!\[redacted\])[^\s,;\"']+", r"\1[redacted]", message
    )
    message = re.sub(
        r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[redacted]", message
    )
    message = re.sub(r"(?<![\w])[A-Za-z0-9_-]{24,}(?![\w])", "[redacted]", message)
    return " ".join(message.split())[:320]
