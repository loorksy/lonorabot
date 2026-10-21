"""Lexical disclosure boundary, not a judge of intent or financial correctness."""

import re
import unicodedata

PRIVATE_NARRATION = re.compile(
    r"\b(?:cards?|widgets?|tools?|skills?|runs?|events?|API|MCP|checkpoints?|leases?|workers?)\b"
    r"|\b(?:approval_id|goal_id|run_id|operation_id|connection_id|pending)\b(?!\s+(?:orders?|buy|sell)\b)"
    r"|(?:بطاق(?:ة|ات)|[اأ]دوات|[اأ]داة|مهارات|[اأ]حداث|واجهات برمجية)"
    r"|\b(?:broker|trade|goal|tool|skill|run|runtime|execution|operation|device|chart|market)_[a-z][a-z0-9_]*\b"
    r"|sandbox:|file://|/mnt/data|<lonora_|<skill_runtime>",
    re.I,
)
PRIVATE_RESOURCE_ID = re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", re.I)


def public_reply_violation(
    text: str, tool_names: set[str] | None = None, *, public_ids: set[str] | None = None
) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKC", text)
        if unicodedata.category(char) not in {"Cf", "Mn"}
    )
    if PRIVATE_NARRATION.search(normalized) or any(
        match[0] not in (public_ids or set()) for match in PRIVATE_RESOURCE_ID.finditer(normalized)
    ):
        return True
    return any(
        re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normalized)
        for name in (tool_names or set())
        if "_" in name
    )
