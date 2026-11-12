"""The owner's model usage, readable in chat (mandate P5 and 13.1).

The same services as the usage page: cost and tokens per agent and per model for a
period in the owner's time zone, and the month to date with its projection. A view,
never a cap (owner decision D4, mandate P1).
"""

from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.usage import UsagePeriod
from lonora_core.user_error import LonoraError
from lonora_db.transactions import owned_agent
from lonora_db.usage import owner_zone, usage_rank, usage_series
from pydantic import Field

from .base import Tool
from .context import ToolContext


class UsageInput(Contract):
    period: UsagePeriod = Field(
        default="month",
        description="day = today so far, week = the last 7 local days, month = the last 30.",
    )
    agent_id: str | None = Field(
        default=None, max_length=36, description="One agent's id; omit for every agent."
    )


async def usage(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = UsageInput.model_validate(args)
    now = utcnow()
    async with context.db.sessions() as session:
        if params.agent_id is not None:
            try:
                await owned_agent(session, context.owner_id, params.agent_id)
            except LonoraError as error:
                return {"ok": False, "code": error.code}
        zone = await owner_zone(session, context.owner_id, None)
        rank = await usage_rank(
            session, context.owner_id, params.period, zone, now, params.agent_id
        )
        series = await usage_series(
            session, context.owner_id, params.period, zone, now, params.agent_id
        )
    return {
        "ok": True,
        **rank.model_dump(mode="json"),
        "previous": series.previous.model_dump(mode="json"),
        "month": series.month.model_dump(mode="json"),
    }


def tools() -> list[Tool]:
    return [
        Tool(
            "usage_read",
            "The owner's model usage: cost in USD and tokens per agent and per model for a "
            "period in the owner's time zone, the previous equal window, and this month so far "
            "with its projection. cost_usd covers models with a list price; unpriced_requests "
            "counts the rest.",
            UsageInput,
            usage,
            True,
        ),
    ]
