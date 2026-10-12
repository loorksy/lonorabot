def should_participate(agent_id: str, mentioned: list[str], lead_id: str | None) -> bool:
    return agent_id in mentioned if mentioned else agent_id == lead_id
