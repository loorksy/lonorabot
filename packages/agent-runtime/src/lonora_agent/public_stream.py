"""Incremental privacy admission; effect claims remain final-only."""

import re
from time import monotonic

from lonora_core.public_reply import public_reply_violation

from .visual_response import visual_stream_prefix

# Disclosure filtering, not user-intent routing or a trading decision rule.
EFFECT_CLAIM = re.compile(
    r"\b(?:executed|opened|closed|placed|bought|sold|approved|confirmed|sent|activated|done|buy|sell|password|secret|credential|authorization|token)\b"
    r"|(?:تنفيذ|نفذ|نُف|أرسلت|ارسلت|فتحت|فتحنا|أغلقت|اغلقت|فعّلت|فعلت|تمت?\s)",
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
        if not self.enabled or len(self.buffer) - len(self.sent) < 8:
            return ""
        # No text can leave during this interval. Defer the costly cumulative
        # disclosure scan until publication is eligible, then check every byte.
        if self.sent and monotonic() - self.last_publish < 0.2:
            return ""
        candidate = visual_stream_prefix(self.buffer)
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
        if len(text) < 8 or (self.sent and monotonic() - self.last_publish < 0.2):
            return ""
        self.sent = candidate[:end]
        self.last_publish = monotonic()
        return text
