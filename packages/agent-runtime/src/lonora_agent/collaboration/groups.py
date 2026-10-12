from .mentions import mentioned_agents
from .participation import should_participate


def group_targets(content: str, members: dict[str, str]) -> list[str]:
    mentioned = mentioned_agents(content, members)
    lead = next(iter(members), None)
    return [agent_id for agent_id in members if should_participate(agent_id, mentioned, lead)]
