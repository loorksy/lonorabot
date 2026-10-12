import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from lonora_core.user_error import LonoraError

SENSITIVE = re.compile(r"password|secret|token|api.?key|authorization|ciphertext", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if SENSITIVE.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
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
