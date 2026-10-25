"""Reject internal narration/identifiers without banning ordinary domain language."""

import re
import unicodedata

# Generic words are not private facts by themselves: economic events, trading
# skills and a third-party day-trader-skill repository are legitimate subjects.
# Reject narration about Lonora's machinery; keep exact identifiers fail-closed.
_OBJECT = r"(?<![\w/-])(?:cards?|widgets?|tools?|skills?|runs?|events?)(?![\w/-])"
PRIVATE_NARRATION = re.compile(
    r"\b(?:approval_id|goal_id|run_id|operation_id|connection_id|pending)\b(?!\s+(?:orders?|buy|sell)\b)"
    r"|\b(?:broker|trade|goal|tool|skill|run|runtime|execution|operation|device|chart|market)_[a-z][a-z0-9_]*\b"
    r"|sandbox:|file://|/mnt/data|<lonora_|<skill_runtime>"
    r"|\b(?:my|our|internal|runtime|system)\s+"
    + _OBJECT
    + r"|\b(?:creat(?:e|ed|ing)|load(?:ed|ing)?|call(?:ed|ing)?|invok(?:e|ed|ing)|emit(?:ted|ting)?|us(?:e|ed|ing)|send(?:ing)?|sent|dispatch(?:ed|ing)?|start(?:ed|ing)?|queu(?:e|ed|ing))\b[^.!?\n]{0,48}"
    + _OBJECT
    + r"|"
    + _OBJECT
    + r"\s+(?:is|are)\s+(?:ready|loaded|running|queued)\b"
    + r"|\b(?:the|a)\s+"
    + _OBJECT
    + r"\s+(?:returned|failed|completed|loaded|started|emitted)\b"
    r"|(?:أي|اي)\s+(?:[اأ]داة|[اأ]دوات|مهارات|بطاق(?:ة|ات))"
    r"|\bwhich\s+"
    + _OBJECT
    + r"|(?:بطاق(?:ة|ات)\s+(?:موافقة|تفويض)|أدواتي|ادواتي|مهاراتي|واجهات برمجية)"
    r"|(?:أرسلت|ارسلت|سأرسل|انشأت|أنشأت|سأنشئ|استدعيت|سأستدعي|استخدمت|سأستخدم|أستخدم|تم تحميل|حملت|حمّلت)[^.!؟\n]{0,40}(?:بطاق(?:ة|ات)|[اأ]دوات|[اأ]داة|مهارات|[اأ]حداث)",
    re.I,
)
TECHNICAL_NOUN = re.compile(r"(?<![\w/-])(?:API|MCP|checkpoints?|leases?|workers?)(?![\w/-])", re.I)
EXTERNAL_SUBJECT = re.compile(
    r"\b(?:external|third-party|repository|project|documentation)\b"
    r"|(?:المشروع|المستودع|مستودع|مشروع|الخارجي|خارجي|توثيق)",
    re.I,
)


def private_technical_narration(text: str) -> bool:
    for match in TECHNICAL_NOUN.finditer(text):
        # External architecture can be discussed; a named private identifier is
        # still rejected separately, regardless of the surrounding subject.
        start = max(text.rfind(mark, 0, match.start()) for mark in (".", "!", "?", "؟", "\n")) + 1
        end = min(
            (
                pos
                for mark in (".", "!", "?", "؟", "\n")
                if (pos := text.find(mark, match.end())) != -1
            ),
            default=len(text),
        )
        sentence = text[max(start, match.start() - 160) : min(end, match.end() + 160)]
        if not EXTERNAL_SUBJECT.search(sentence):
            return True
    return False


PRIVATE_RESOURCE_ID = re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", re.I)


def public_reply_violation(
    text: str, tool_names: set[str] | None = None, *, public_ids: set[str] | None = None
) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKC", text)
        if unicodedata.category(char) not in {"Cf", "Mn"}
    )
    if (
        PRIVATE_NARRATION.search(normalized)
        or private_technical_narration(normalized)
        or any(
            match[0] not in (public_ids or set())
            for match in PRIVATE_RESOURCE_ID.finditer(normalized)
        )
    ):
        return True
    return any(
        re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normalized)
        for name in (tool_names or set())
        if "_" in name
    )
