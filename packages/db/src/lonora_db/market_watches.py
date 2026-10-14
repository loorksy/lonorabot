from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.market_watch import Watch
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow, MarketWatchRow
from .threads import create_thread
from .trading_goals import owned_goal, planned_step
from .transactions import ResourceRepository, ResourceRow, owned_thread


class MarketWatchRepository(ResourceRepository):
    row_type = MarketWatchRow
    kind = "market_watches"
    payload_model = Watch

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        await super().validate_references(session, owner_id, payload)
        if payload.get("integration_id"):
            source = await session.get(IntegrationRow, payload["integration_id"])
            if (
                source is None
                or source.owner_id != owner_id
                or source.payload.get("type") != "economic_calendar"
            ):
                raise LonoraError("calendar_integration_not_found", 404)

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        if not agent_id:
            raise LonoraError("watch_agent_required", 422)
        if payload.get("goal_id"):
            goal = await owned_goal(session, owner_id, str(payload["goal_id"]))
            if thread_id and thread_id != goal.thread_id or agent_id != goal.agent_id:
                raise LonoraError("goal_run_mismatch", 409)
            thread_id = goal.thread_id
            await owned_thread(session, owner_id, thread_id or "", lock=True)
            planned_step(goal, payload.get("step_id"))
            payload = {**payload, "goal_plan_version": int(goal.state.get("plan_version", 1))}
        if not thread_id:
            thread = await create_thread(
                session,
                owner_id,
                ThreadCreate(
                    agent_id=agent_id,
                    title=str(payload.get("prompt", ""))[:80],
                ),
            )
            thread_id = thread.id
        return await super().create(
            session,
            owner_id,
            payload,
            agent_id=agent_id,
            thread_id=thread_id,
            resource_id=resource_id,
        )
