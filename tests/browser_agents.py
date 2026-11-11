"""Browser-spec helper: keep test agents from piling up against the owner's agent cap.

Agents an agent creates are capped at ``MAXIMUM_ACTIVE_AGENTS`` active (not paused) agents
per owner. ``{"action": "pause", "ids": [...]}`` pauses agents a spec cannot delete (an
uncertain trade rightly refuses deletion); ``{"action": "headroom", "needed": n}`` pauses the
oldest active non-personal agents until ``n`` more fit. Pausing removes nothing. The specs
run one at a time, so no other spec is using what this pauses.
"""

import asyncio
import json
import sys
from typing import Any

from check_streaming import Fixture
from lonora_db.agent_creation import MAXIMUM_ACTIVE_AGENTS, active_agents
from lonora_db.schema import AgentRow
from sqlalchemy import select


async def action(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            if data["action"] == "pause":
                wanted = select(AgentRow).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.id.in_(data["ids"])
                )
            elif data["action"] == "headroom":
                excess = await active_agents(session, fixture.owner) - (
                    MAXIMUM_ACTIVE_AGENTS - int(data.get("needed", 1))
                )
                wanted = (
                    select(AgentRow)
                    .where(
                        AgentRow.owner_id == fixture.owner,
                        AgentRow.role.not_in(["personal", "delegated"]),
                        AgentRow.paused.is_(False),
                    )
                    .order_by(AgentRow.created_at)
                    .limit(max(excess, 0))
                )
            else:
                raise ValueError("Unknown browser agents action")
            paused: list[str] = []
            for row in await session.scalars(wanted.with_for_update()):
                row.paused = True
                paused.append(row.id)
            return {"paused": paused}
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
