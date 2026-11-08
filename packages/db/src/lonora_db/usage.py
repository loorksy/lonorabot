from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, UsageRow
from .transactions import ResourceRepository

TOKEN_KEYS = ("input_tokens", "output_tokens", "cached_tokens")


class UsageRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for usage."""

    row_type = UsageRow
    kind = "usage"


async def agent_usage(
    session: AsyncSession, owner_id: str, since: datetime, agent_id: str | None = None
) -> list[dict[str, Any]]:
    """Model usage per Agent since ``since``, from the recorded requests: tokens and
    requests in total and per model, largest first. A view, never a cap (owner D4)."""
    provider = UsageRow.payload["provider"].as_string()
    model = UsageRow.payload["model"].as_string()
    query = (
        select(
            UsageRow.agent_id,
            provider.label("provider"),
            model.label("model"),
            func.count().label("requests"),
            func.max(UsageRow.created_at).label("last_used_at"),
            *(
                func.coalesce(func.sum(UsageRow.payload[key].as_integer()), 0).label(key)
                for key in TOKEN_KEYS
            ),
        )
        .where(UsageRow.owner_id == owner_id, UsageRow.created_at >= since)
        .group_by(UsageRow.agent_id, provider, model)
    )
    if agent_id is not None:
        query = query.where(UsageRow.agent_id == agent_id)
    rows = (await session.execute(query)).mappings().all()
    names = {
        row.id: row.name
        for row in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id))
    }
    agents: dict[str | None, dict[str, Any]] = {}
    for row in rows:
        entry = agents.setdefault(
            row["agent_id"],
            {
                "agent_id": row["agent_id"],
                "agent_name": names.get(row["agent_id"]) if row["agent_id"] else None,
                "requests": 0,
                "last_used_at": None,
                **dict.fromkeys(TOKEN_KEYS, 0),
                "models": [],
            },
        )
        tokens = {key: int(row[key]) for key in TOKEN_KEYS}
        entry["requests"] += int(row["requests"])
        for key in TOKEN_KEYS:
            entry[key] += tokens[key]
        last = row["last_used_at"]
        if last is not None and (entry["last_used_at"] is None or last > entry["last_used_at"]):
            entry["last_used_at"] = last
        entry["models"].append(
            {
                "provider": row["provider"],
                "model": row["model"],
                "requests": int(row["requests"]),
                **tokens,
            }
        )
    result = sorted(
        agents.values(),
        key=lambda item: (
            -(item["input_tokens"] + item["output_tokens"]),
            item["agent_name"] or "",
        ),
    )
    for item in result:
        models = cast(list[dict[str, Any]], item["models"])
        models.sort(key=lambda model: -(model["input_tokens"] + model["output_tokens"]))
        item["last_used_at"] = item["last_used_at"].isoformat() if item["last_used_at"] else None
    return result
