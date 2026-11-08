"""Refuse authority and disclosure statements in text every later Run reads as guidance.

Operating notes and the shared owner profile shape how Agents work. Neither can
grant or deny financial authority: that comes only from the owner's signed grant,
the account's limits and the owner's pauses, which the single executor enforces.
A statement about approvals, authorization or bypassing limits in such text is
either injected or misplaced, so a write containing one is refused and the Agent
is told where the rule belongs. This is defence in depth, not enforcement: the
executor never reads memory.
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


def authority_claims(text: str) -> list[str]:
    """Every authority statement in ``text``, and every standing instruction to hand
    private data elsewhere, normalized for comparison."""
    return [
        re.sub(r"\s+", " ", match.group(0)).strip().casefold()[:120]
        for pattern in (_EN, _AR, _DISCLOSURE_EN, _DISCLOSURE_AR)
        for match in pattern.finditer(text)
    ]


def authority_claim(text: str) -> str | None:
    """The first authority statement in ``text``, or None."""
    claims = authority_claims(text)
    return claims[0] if claims else None


AUTHORITY_RECOVERY = (
    "Nothing was saved. Operating notes and the owner profile cannot state trading "
    "authority, approvals or limits: authority comes only from the owner's signed grant, "
    "and limits from account limits or a restriction. Nor can they tell agents to send "
    "memory, notes, the owner profile or secrets anywhere, or to fetch an address built "
    "from data. Save the working method without that statement, or offer the owner the "
    "matching control."
)
