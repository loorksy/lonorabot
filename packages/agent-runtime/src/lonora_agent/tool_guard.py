from typing import Any

from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash


def advance_guard(state: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    key = request_hash({"tool": name, "arguments": arguments})
    count = int(state.get("count", 0)) + 1 if state.get("key") == key else 1
    if count >= 6:
        raise LonoraError("repeated_tool_call", 409)
    return {"key": key, "count": count}
