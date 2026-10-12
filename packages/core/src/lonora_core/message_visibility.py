def visible(trigger: str, role: str) -> bool:
    return trigger != "tickets" and role != "tool"
