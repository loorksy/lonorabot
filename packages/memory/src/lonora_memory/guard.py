"""Refuse standing instructions to hand private data elsewhere in text every later Run
reads as guidance (an Agent's method and the shared owner profile).

Such a line is injected or misplaced, so a memory write that adds one is refused.
A method may say anything about trading, approvals or confirmation: the owner's
strategy is the Agent's method (5.6), and the execution door reads grants and approvals,
never memory. ``authority_claim`` still serves the agent-creation responsibility check.
"""

import re

_EN = re.compile(
    r"\b(?:"
    r"(?:without|skip(?:ping)?|bypass(?:ing)?|ignor(?:e|ing)|disregard(?:ing)?)\s+"
    r"(?:the\s+|any\s+|an\s+|my\s+|owner(?:'s)?\s+)?"
    r"(?:approvals?|confirmations?|passkeys?|signatures?|grants?|permissions?)"
    r"|no\s+(?:approvals?|confirmations?|passkeys?|signatures?|permissions?)\s+"
    r"(?:is\s+|are\s+)?(?:needed|required|necessary)"
    r"|(?:authori[sz]ed|permitted|allowed|cleared|free)\s+to\s+"
    r"(?:trade|execute|place|open|buy|sell|send|close)"
    r"|owner\s+(?:has\s+|already\s+)?(?:approved|authori[sz]ed|allowed|granted|consented)"
    r"|(?:override|overrides|overriding|bypass|bypasses|ignore|ignores|disregard)\s+"
    r"(?:the\s+|any\s+|all\s+|every\s+|my\s+|your\s+|its\s+)?(?:system\s+|owner(?:'s)?\s+)?"
    r"(?:polic(?:y|ies)|limits?|restrictions?|pauses?|brakes?|grants?|instructions?|rules?)"
    r"|(?:full|unlimited|unrestricted|absolute)\s+(?:trading\s+|financial\s+|execution\s+)?"
    r"(?:authority|authori[sz]ation|permissions?|autonomy)"
    r")\b",
    re.IGNORECASE,
)
_AR = re.compile(
    r"(?:بدون|بلا|دون|من\s+غير)\s+(?:أخذ\s+|طلب\s+)?(?:ال)?(?:موافقة|إذن|اذن|تأكيد|توقيع|تفويض)"
    r"|(?:مفو[َّ]?ض|مصر[َّ]?ح|مسموح)\s+(?:لك\s+|لي\s+|له\s+|لها\s+)?(?:بال|ب|في\s+ال)?"
    r"(?:تداول|تنفيذ|فتح|شراء|بيع)"
    r"|(?:وافق|فو[َّ]?ض|سمح|أذن)\s+(?:ال)?(?:مالك|مستخدم)"
    r"|(?:^|\s)[وف]?(?:تجاهل|تجاوز|اكسر|تخط[َّ]?)\s+(?:كل\s+)?(?:ال)?"
    r"(?:حدود|حد|قيود|تعليمات|سياسة|إيقاف|فرامل|تفويض|موافقة)"
    r"|صلاحي[ةه]\s+(?:كاملة|مطلقة|غير\s+محدودة)"
)


# Standing instructions to hand private data elsewhere: send an agent's memory, notes,
# the owner profile or secrets somewhere, fetch an address built from data, or a tool
# name. Every agent reads this text as guidance, so such a line is injected or misplaced.
_DISCLOSURE_EN = re.compile(
    r"\b(?:send|forward|share|post|upload|copy|leak|exfiltrat\w*|transmit|dump|relay)\s+"
    r"(?:[^\s]+\s+){0,5}?"
    r"(?:(?:its|your|their|full|whole|entire|private|the)\s+)?"
    r"(?:memory(?:\.md)?|operating(?:\.md|\s+notes)|user\.md|owner\s+profile|private\s+notes"
    r"|secrets?|api\s+keys?|keys|tokens?|credentials?|passwords?)\b"
    r"|https?://[^\s]*?(?:[<{][^\s<>{}]*[>}])"
    r"|\bpeer_send\b",
    re.IGNORECASE,
)
_DISCLOSURE_AR = re.compile(
    r"(?:أرسل|ارسل|شارك|انشر|حو[ّ]?ل|سر[ّ]?ب|انسخ)\s+(?:[^\s]+\s+){0,4}?"
    r"(?:ال)?(?:ذاكرة|ذاكرتك|ذاكرته|ملاحظات\s+التشغيل|ملف\s+المالك|أسرار|مفاتيح|كلمات\s+المرور"
    r"|بيانات\s+الدخول)"
)


def _claims(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    return [
        re.sub(r"\s+", " ", match.group(0)).strip().casefold()[:120]
        for pattern in patterns
        for match in pattern.finditer(text)
    ]


def disclosure_claims(text: str) -> list[str]:
    """Every standing instruction in ``text`` to hand private data elsewhere, normalized
    for comparison."""
    return _claims(text, (_DISCLOSURE_EN, _DISCLOSURE_AR))


def authority_claim(text: str) -> str | None:
    """The first authority or disclosure statement in ``text``, or None."""
    claims = _claims(text, (_EN, _AR, _DISCLOSURE_EN, _DISCLOSURE_AR))
    return claims[0] if claims else None


DISCLOSURE_RECOVERY = (
    "Nothing was saved. Your method and the owner profile cannot tell agents to send "
    "memory, notes, the owner profile or secrets anywhere, or to fetch an address built "
    "from data. Save the method without that line."
)
