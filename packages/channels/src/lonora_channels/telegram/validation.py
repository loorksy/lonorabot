import secrets

from lonora_core.user_error import LonoraError


def verify_webhook_token(supplied: str | None, expected: str) -> None:
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise LonoraError("telegram_webhook_forbidden", 403)
