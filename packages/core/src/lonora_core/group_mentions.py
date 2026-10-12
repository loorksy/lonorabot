import re


def mentions(content: str, agents: dict[str, str]) -> list[str]:
    result: list[str] = []
    for agent_id, name in agents.items():
        if re.search(r"@" + re.escape(name) + r"(?=$|[\s,،.!?])", content, re.IGNORECASE):
            result.append(agent_id)
    return result
