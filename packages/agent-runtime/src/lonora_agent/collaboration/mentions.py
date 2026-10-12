from lonora_core.group_mentions import mentions


def mentioned_agents(content: str, members: dict[str, str]) -> list[str]:
    return mentions(content, members)
