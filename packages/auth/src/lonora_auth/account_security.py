from lonora_core.user_error import LonoraError
from pwdlib import PasswordHash

HASHER = PasswordHash.recommended()
DUMMY_HASH = HASHER.hash("lonora-invalid-account-password")


def normalize_email(email: str) -> str:
    clean = email.strip().lower()
    if clean.count("@") != 1 or not all(clean.split("@")) or len(clean) > 254:
        raise LonoraError("invalid_email", 422)
    return clean


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise LonoraError("invalid_password", 422)
    return HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return HASHER.verify(password, encoded)
    except Exception:
        return False
