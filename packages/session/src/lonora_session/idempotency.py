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


def broker_operation_tag(operation_id: str) -> str:
    """Stable broker correlation id.

    MetaApi stores this in the order comment as strategyId_positionId_orderId and rejects any
    other shape. The tag stays within the 31-character comment budget.
    """
    digest = hashlib.sha256(operation_id.encode()).hexdigest()
    return "LN_" + digest[:12] + "_" + digest[12:24]
