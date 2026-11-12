import base64
import re
from collections.abc import Mapping
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


B64_TAIL = r"[A-Za-z0-9+/_-]{1,3}={0,2}"


def secret_forms(value: str) -> list[str]:
    """Patterns for a value and its base64, hex and URL-encoded forms. A base64 form
    also matches when more bytes follow the value (``echo "$KEY" | base64``)."""
    raw = value.encode()
    forms = [value, raw.hex(), raw.hex().upper(), quote(value, safe=""), quote_plus(value)]
    patterns = [re.escape(form) for form in forms]
    for encode in (base64.b64encode, base64.urlsafe_b64encode):
        full = encode(raw).decode()
        whole = 4 * (len(raw) // 3)
        if len(raw) % 3 == 0:
            patterns.append(re.escape(full))
        elif whole:
            # The full groups and the next character depend only on the value.
            patterns.append(re.escape(full[: whole + 1]) + B64_TAIL)
        else:
            patterns += [re.escape(full), re.escape(full.rstrip("="))]
    return patterns


class SecretScan:
    """Replaces each named secret's value and its encoded forms with ``[secret:NAME]``.
    A program that transforms a value any other way can defeat it (VISION.md 7.2.6)."""

    def __init__(self, secrets: Mapping[str, str]):
        alternatives: list[tuple[int, str, str]] = []
        for name, value in secrets.items():
            if value:
                for form in dict.fromkeys(secret_forms(value)):
                    alternatives.append((len(form), form, name))
        # Longer forms first: a value's base64 form is not cut short by the value itself.
        alternatives.sort(key=lambda item: -item[0])
        self.names = {"s" + str(i): name for i, (_, _, name) in enumerate(alternatives)}
        self.pattern = (
            re.compile("|".join(f"(?P<s{i}>{part})" for i, (_, part, _) in enumerate(alternatives)))
            if alternatives
            else None
        )
        self.raw = (
            re.compile(self.pattern.pattern.encode("utf-8")) if self.pattern is not None else None
        )

    def text(self, text: str) -> str:
        if self.pattern is None:
            return text
        return self.pattern.sub(lambda m: f"[secret:{self.names[m.lastgroup or '']}]", text)

    def found(self, data: bytes) -> bool:
        return self.raw is not None and self.raw.search(data) is not None
