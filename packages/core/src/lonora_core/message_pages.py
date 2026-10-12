from typing import Any


def page_messages(
    messages: list[dict[str, Any]], before: int | None, limit: int
) -> list[dict[str, Any]]:
    eligible = [item for item in messages if before is None or int(item["seq"]) < before]
    return sorted(eligible, key=lambda item: int(item["seq"]))[-max(1, min(limit, 200)) :]
