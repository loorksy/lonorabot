import hashlib
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5


def stable_id(scope: str, nonce: str) -> str:
    return str(uuid5(NAMESPACE_URL, scope + ":" + nonce))


def request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
