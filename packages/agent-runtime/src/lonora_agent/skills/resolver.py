from typing import Any


def enabled_skills(built_in: dict[str, str], installed: list[dict[str, Any]]) -> dict[str, str]:
    selected = dict(built_in)
    for item in installed:
        if item.get("enabled", True):
            selected[str(item["name"])] = str(item["content"])
        else:
            selected.pop(str(item["name"]), None)
    return selected
