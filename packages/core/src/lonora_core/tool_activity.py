from typing import Any


def tool_activity(
    name: str, call_id: str, status: str, summary: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"tool": name, "call_id": call_id, "status": status, "summary": summary or {}}
