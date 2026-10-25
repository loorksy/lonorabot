"""Hard output privacy only; conversational style never decides task success.

Public capability names and ordinary diagnostic vocabulary are not credentials.
Presentation is owned by the model's instructions, not a keyword veto on replies.
"""

import re
import unicodedata

PRIVATE_RESOURCE_ID = re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", re.I)
PRIVATE_LOCATION = re.compile(
    r"(?:sandbox:|file://)[^\s<>\"'\])]*"
    r"|(?<![\w:/])/(?:mnt/data|opt/lonora|workspace|tmp|app/packages|app/apps)(?![\w.-])(?:/[^\s<>\"'\])]*)?"
    r"|</?(?:lonora_[a-z_]+|skill_runtime)[^>]*>",
    re.I,
)
CREDENTIAL = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)"
    r"|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"
    r"|\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]{1,}"
    r"|\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|auth[_ -]?token|token|secret|authorization)\s*[:=]\s*[\"']?[^\s,;\"'<>]{1,}"
    r"|كلمة\s+(?:السر|المرور)\s*[:=]\s*[\"']?[^\s,;\"'<>]{1,}",
    re.I,
)
REDACTED = "[REDACTED]"


def normalized_text(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", text)
        if unicodedata.category(char) not in {"Cf", "Mn"}
    )


def public_reply_violation(
    text: str, tool_names: set[str] | None = None, *, public_ids: set[str] | None = None
) -> bool:
    # Retain the old call shape for consumers; registry names are intentionally
    # not private. Inspecting/describing an operation never grants its authority.
    del tool_names
    normalized = normalized_text(text)
    return bool(
        CREDENTIAL.search(normalized)
        or PRIVATE_LOCATION.search(normalized)
        or any(
            match[0] not in (public_ids or set())
            for match in PRIVATE_RESOURCE_ID.finditer(normalized)
        )
    )


def redact_private_reply(text: str, *, public_ids: set[str] | None = None) -> str:
    """Remove sensitive spans, without a second model call or losing the answer.

    Safe replies are byte-for-byte unchanged. Normalize only unsafe output so
    zero-width/combining characters cannot bypass the same privacy boundary.
    No replacement adds facts, grants permissions or changes a broker outcome.
    """
    if not public_reply_violation(text, public_ids=public_ids):
        return text
    protected = CREDENTIAL.sub(REDACTED, normalized_text(text))
    protected = PRIVATE_LOCATION.sub(REDACTED, protected)
    return PRIVATE_RESOURCE_ID.sub(
        lambda match: match[0] if match[0] in (public_ids or set()) else REDACTED, protected
    )
