"""Incremental privacy admission; effect claims remain final-only."""

import re
from time import monotonic

from lonora_core.public_reply import public_reply_violation

from .visual_response import visual_stream_prefix

# Disclosure filtering, not user-intent routing or a trading decision rule.
EFFECT_CLAIM = re.compile(
    r"\b(?:I|we)\s+(?:have\s+)?(?:executed|opened|closed|placed|bought|sold|approved|sent|activated)\b"
    r"|\b(?:order|trade|position|request|super\s*bot)\s+(?:(?:has\s+been|was|is|successfully)\s+){0,2}(?:executed|opened|closed|placed|approved|sent|activated|confirmed|completed)\b"
    r"|\b(?:executed|opened|closed|placed|bought|sold)\s+(?:(?:the|a|your|buy|sell|market)\s+){0,3}(?:order|trade|position)\b"
    r"|^(?:Done|Completed|Confirmed|Approved)[.!]?(?:\s|$)"
    r"|(?:تمت?\s+(?:تنفيذ|فتح|إغلاق|اغلاق|إرسال|ارسال|تفعيل|شراء|بيع|الموافقة))"
    r"|(?:فتحت|فتحنا|أغلقت|اغلقت|نفذت|نفّذت|فعّلت|فعلت|أرسلت|ارسلت)\s+(?:(?:لك|بنجاح|الآن|الان)\s+)?(?:صفقة|أمر|امر|السوبر|سوبر)",
    re.IGNORECASE,
)


class PublicStream:
    def __init__(self, names: set[str], public_ids: set[str], *, enabled: bool):
        self.names, self.public_ids, self.enabled = names, public_ids, enabled
        self.buffer = ""
        self.sent = ""
        self.last_publish = 0.0

    def feed(self, chunk: str) -> str:
        self.buffer += chunk
        return self.offer(visual_stream_prefix(self.buffer))

    def offer(self, candidate: str, *, complete_boundary: bool = False) -> str:
        """Admit a cumulative compiler projection, never serialized UI.

        Complete validated component boundaries can publish even when their text
        alternative is short. Privacy and execution-truth admission still apply.
        """
        if not self.enabled or not candidate.startswith(self.sent):
            return ""
        if not complete_boundary and len(candidate) - len(self.sent) < 8:
            return ""
        # No text can leave during this interval. Defer the costly cumulative
        # disclosure scan until publication is eligible, then check every byte.
        if not complete_boundary and self.sent and monotonic() - self.last_publish < 0.2:
            return ""
        if EFFECT_CLAIM.search(candidate) or public_reply_violation(
            candidate, self.names, public_ids=self.public_ids
        ):
            self.enabled = False
            return ""
        # Admit complete words, never half an internal identifier. Bound writes
        # by time and characters rather than provider token framing.
        boundaries = list(re.finditer(r"\s+", candidate))
        if not boundaries:
            return ""
        end = boundaries[-1].end()
        text = candidate[len(self.sent) : end]
        if not complete_boundary and (
            len(text) < 8 or (self.sent and monotonic() - self.last_publish < 0.2)
        ):
            return ""
        self.sent = candidate[:end]
        self.last_publish = monotonic()
        return text
