"""Per-agent delivery rules (owner decision Q47) and the gate owner alerts pass through."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from lonora_contracts.agent_delivery import AgentDeliveryRules, AgentDeliveryRulesUpdate
from lonora_contracts.domain import utcnow
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentDeliveryRulesRow, EventRow
from .transactions import owned_agent

URGENT = frozenset({"critical", "action_required"})


def rules_data(row: AgentDeliveryRulesRow | None) -> AgentDeliveryRules:
    if row is None:
        return AgentDeliveryRules()
    return AgentDeliveryRules(in_app=row.in_app, calls=row.calls, daily_limit=row.daily_limit)


async def delivery_rules(session: AsyncSession, owner_id: str, agent_id: str) -> AgentDeliveryRules:
    return rules_data(await session.get(AgentDeliveryRulesRow, (owner_id, agent_id)))


async def all_delivery_rules(session: AsyncSession, owner_id: str) -> dict[str, AgentDeliveryRules]:
    rows = await session.scalars(
        select(AgentDeliveryRulesRow).where(AgentDeliveryRulesRow.owner_id == owner_id)
    )
    return {row.agent_id: rules_data(row) for row in rows}


async def set_delivery_rules(
    session: AsyncSession, owner_id: str, agent_id: str, change: AgentDeliveryRulesUpdate
) -> AgentDeliveryRules:
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(AgentDeliveryRulesRow, (owner_id, agent_id), with_for_update=True)
    if row is None:
        row = AgentDeliveryRulesRow(owner_id=owner_id, agent_id=agent_id, in_app=True, calls=True)
        session.add(row)
    for field in ("in_app", "calls"):
        value = getattr(change, field)
        if value is not None:
            setattr(row, field, value)
    if "daily_limit" in change.model_fields_set:
        row.daily_limit = change.daily_limit
    row.updated_at = utcnow()
    await session.flush()
    return rules_data(row)


def local_midnight(now: datetime, timezone: str) -> datetime:
    local = now.astimezone(ZoneInfo(timezone))
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


async def delivery_block(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    importance: str,
    *,
    event_kind: str,
    timezone: str,
    now: datetime | None = None,
) -> str | None:
    """Why this agent's alert stays in Activity only, or None when it may show.

    Urgent items always show. The daily limit counts the agent's earlier non-urgent alerts
    since the owner's local midnight (the alert being decided is not yet recorded)."""
    if importance in URGENT:
        return None
    rules = await delivery_rules(session, owner_id, agent_id)
    if not rules.in_app:
        return "agent_in_app_off"
    if rules.daily_limit is None:
        return None
    since = local_midnight(now or utcnow(), timezone)
    count = await session.scalar(
        select(func.count())
        .select_from(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.agent_id == agent_id,
            EventRow.kind == event_kind,
            EventRow.created_at >= since,
            EventRow.created_at < since + timedelta(days=1, hours=1),
            EventRow.payload["importance"].as_string().not_in(sorted(URGENT)),
        )
    )
    return "agent_daily_limit" if (count or 0) >= rules.daily_limit else None
