import hashlib
import hmac
import re

from lonora_core.user_error import LonoraError
from pwdlib import PasswordHash

HASHER = PasswordHash.recommended()
DUMMY_HASH = HASHER.hash("lonora-invalid-account-password")
# Lonora Cloud (docs/cloud/DECISIONS.md D48): the owner of a new installation is the website account
# that asked for it, with that account's password as the website stores it
# (cloud/site/functions/_lib/core.js hashPassword), so the customer signs up once. The first
# sign-in here replaces it with this server's own hash.
SITE_HASH = re.compile(r"^pbkdf2-sha256\$([1-9][0-9]{4,6})\$([0-9a-f]{16,64})\$([0-9a-f]{64})$")


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
    if site := SITE_HASH.match(encoded):
        iterations, salt, digest = site.groups()
        derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(derived.hex(), digest)
    try:
        return HASHER.verify(password, encoded)
    except Exception:
        return False


def kept_hash(password: str, encoded: str) -> str:
    """The hash to keep once ``password`` matched ``encoded``: the website's is replaced by this
    server's own (no length rule here: the password is already the owner's)."""
    return HASHER.hash(password) if SITE_HASH.match(encoded) else encoded
