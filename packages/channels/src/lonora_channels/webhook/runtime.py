import hashlib
import hmac

from lonora_core.user_error import LonoraError


def verify_signature(body: bytes, supplied: str | None, secret: str) -> None:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise LonoraError("webhook_signature_invalid", 403)
