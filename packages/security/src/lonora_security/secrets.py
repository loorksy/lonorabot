import base64
import bisect
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote, quote_plus

from cryptography.fernet import Fernet, InvalidToken
from lonora_core.user_error import LonoraError

SENSITIVE = re.compile(r"password|secret|token|api.?key|authorization|ciphertext", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if SENSITIVE.search(str(k)) else redact(v)
            for k, v in cast(dict[str, Any], value).items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in cast(list[Any], value)]
    if isinstance(value, str):
        return re.sub(r"(?i)(Bearer\s+)[^\s]+", r"\1[redacted]", value)
    return value


class SecretCipher:
    def __init__(self, key: str):
        try:
            self.cipher = Fernet(key.encode())
        except ValueError:
            raise LonoraError("encryption_key_invalid", 500) from None

    def encrypt(self, value: str) -> str:
        return self.cipher.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken:
            raise LonoraError("secret_decryption_failed", 500) from None


B64_ALPHABET = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/-_")
LINE_BREAKS = "\r\n"


@dataclass(frozen=True)
class SecretForm:
    """One way a secret's value can appear in text.

    ``wrapped`` forms (hex, base64) are also found when tools wrap them across lines
    (``base64`` at 76 columns, ``xxd -p`` at 60). A base64 ``core`` holds only the
    characters that depend on the value alone; ``left``/``right`` say a character
    mixing value bits with neighbouring bytes sits before or after it.
    """

    text: str
    name: str
    wrapped: bool = False
    left: bool = False
    right: bool = False


def lower_escapes(text: str) -> str:
    return re.sub(r"%[0-9A-F]{2}", lambda escape: escape[0].lower(), text)


def base64_forms(raw: bytes, name: str) -> list[SecretForm]:
    """The value's base64 at each of the three byte alignments, standard and URL-safe:
    the value encoded alone, after other bytes (``KEY=...``) and before more bytes
    (``echo "$KEY" | base64``)."""
    forms: list[SecretForm] = []
    for encode in (base64.b64encode, base64.urlsafe_b64encode):
        exact = encode(raw).decode()
        for shift in (0, 1, 2):
            encoded = encode(bytes(shift) + raw).decode()
            bits = 8 * (shift + len(raw))
            first, last = -(-8 * shift // 6), (bits - 6) // 6
            core = encoded[first : last + 1]
            if len(core) >= 3:
                forms.append(SecretForm(core, name, True, left=shift > 0, right=bits % 6 != 0))
            elif shift == 0:
                # Too short for a core: its own base64 form, padded or not.
                forms += [SecretForm(exact, name), SecretForm(exact.rstrip("="), name)]
    return forms


def secret_forms(name: str, value: str) -> list[SecretForm]:
    """A value and its base64, hex and URL-encoded forms (and its JSON string form)."""
    raw = value.encode()
    plain = {
        value,
        quote(value, safe=""),
        quote(value),
        quote(value, safe="!*'()"),
        quote_plus(value),
        json.dumps(value)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
    }
    plain |= {lower_escapes(form) for form in plain}
    forms = [SecretForm(form, name) for form in sorted(plain) if form]
    forms += [SecretForm(raw.hex(), name, True), SecretForm(raw.hex().upper(), name, True)]
    return forms + base64_forms(raw, name)


class Squeezed:
    """Text without line breaks, mapping its positions back to the original text."""

    def __init__(self, text: str):
        self.text = text.translate({10: None, 13: None})
        self.starts: list[int] = []
        self.origins: list[int] = []
        position = 0
        for run in re.finditer(r"[^\r\n]+", text):
            self.starts.append(position)
            self.origins.append(run.start())
            position += run.end() - run.start()

    def origin(self, position: int) -> int:
        index = bisect.bisect_right(self.starts, position) - 1
        return self.origins[index] + position - self.starts[index]

    def span(self, start: int, end: int) -> tuple[int, int]:
        return self.origin(start), self.origin(end - 1) + 1


def occurrences(text: str, form: str) -> list[int]:
    found: list[int] = []
    index = text.find(form)
    while index != -1:
        found.append(index)
        index = text.find(form, index + 1)
    return found


def widened(text: str, start: int, end: int, form: SecretForm) -> tuple[int, int]:
    """A base64 core with the characters that still carry some of the value's bits."""
    if form.left and start > 0 and ord(text[start - 1]) in B64_ALPHABET:
        start -= 1
    if form.right and end < len(text) and ord(text[end]) in B64_ALPHABET:
        end += 1
        while end < len(text) and text[end] == "=" and end - start < len(form.text) + 4:
            end += 1
    return start, end


class SecretScan:
    """Replaces each named secret's value and its encoded forms with ``[secret:NAME]``.
    A program that transforms a value any other way can defeat it (VISION.md 7.2.6).

    Every occurrence of every form is found first; overlapping matches merge into one
    marker, so one secret never hides part of another."""

    def __init__(self, secrets: Mapping[str, str]):
        forms = [
            form for name, value in secrets.items() if value for form in secret_forms(name, value)
        ]
        self.plain = [form for form in forms if not form.wrapped]
        self.wrapped = [form for form in forms if form.wrapped]
        self.separable = not any("\x00" in form.text for form in forms)

    def spans(self, text: str) -> list[tuple[int, int, str]]:
        spans = [
            (index, index + len(form.text), form.name)
            for form in self.plain
            for index in occurrences(text, form.text)
        ]
        if self.wrapped:
            squeezed = Squeezed(text) if any(c in text for c in LINE_BREAKS) else None
            flat = squeezed.text if squeezed else text
            for form in self.wrapped:
                for index in occurrences(flat, form.text):
                    start, end = widened(flat, index, index + len(form.text), form)
                    if squeezed:
                        start, end = squeezed.span(start, end)
                    spans.append((start, end, form.name))
        return spans

    def text(self, text: str) -> str:
        spans = sorted(self.spans(text)) if text else []
        if not spans:
            return text
        merged: list[list[Any]] = []
        for start, end, name in spans:
            if merged and start < merged[-1][1]:
                current = merged[-1]
                if end - start > current[3]:
                    current[2], current[3] = name, end - start
                current[1] = max(current[1], end)
            else:
                merged.append([start, end, name, end - start])
        pieces: list[str] = []
        position = 0
        for start, end, name, _ in merged:
            pieces += [text[position:start], f"[secret:{name}]"]
            position = end
        return "".join(pieces) + text[position:]

    def texts(self, texts: list[str]) -> list[str]:
        """Many short strings (file paths) in one pass. NUL separates them: no form
        holds it and a base64 edge never crosses it."""
        if not texts:
            return []
        if not self.separable or any("\x00" in text for text in texts):
            return [self.text(text) for text in texts]
        return self.text("\x00".join(texts)).split("\x00")

    def data(self, value: Any) -> Any:
        """Every string inside a JSON-like value (keys included), scanned."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {self.text(str(k)): self.data(v) for k, v in cast(dict[Any, Any], value).items()}
        if isinstance(value, (list, tuple)):
            return [self.data(item) for item in cast(list[Any], value)]
        return value

    def found(self, data: bytes) -> bool:
        """Whether bytes that cannot be rewritten (an image) carry a secret."""
        if any(form.text.encode() in data for form in self.plain):
            return True
        flat = data.replace(b"\r", b"").replace(b"\n", b"")
        return any(form.text.encode() in flat for form in self.wrapped)
