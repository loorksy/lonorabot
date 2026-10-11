import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from .config import Settings

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("lonora-invalid-account-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def issue_access_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, int]:
    expires_in = settings.auth_token_ttl_seconds
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_in


def read_access_token(token: str, settings: Settings) -> uuid.UUID:
    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"require": ["sub", "iat", "exp"]},
    )
    return uuid.UUID(claims["sub"])
