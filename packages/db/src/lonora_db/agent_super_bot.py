"""Read-only presentation of verified capability, never an execution grant."""

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    AccountAuthorityRow,
    AgentRow,
    DeviceCredentialRow,
    SuperBotRequestRow,
    TradingGoalRow,
)
from .super_bot import require_goal_authority


async def active_super_bot_agents(session: AsyncSession, owner_id: str) -> set[str]:
    candidates = (
        await session.execute(
            select(SuperBotRequestRow, TradingGoalRow, DeviceCredentialRow)
            .join(TradingGoalRow, TradingGoalRow.id == SuperBotRequestRow.goal_id)
            .join(DeviceCredentialRow, DeviceCredentialRow.id == SuperBotRequestRow.device_id)
            .where(
                SuperBotRequestRow.owner_id == owner_id,
                TradingGoalRow.owner_id == owner_id,
                DeviceCredentialRow.owner_id == owner_id,
                SuperBotRequestRow.status == "activated",
                DeviceCredentialRow.revoked.is_(False),
            )
        )
    ).all()
    from .account_authority import require_authority

    result: set[str] = set()
    account_grants = await session.scalars(
        select(AccountAuthorityRow)
        .join(DeviceCredentialRow, DeviceCredentialRow.id == AccountAuthorityRow.device_id)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.status == "active",
            AccountAuthorityRow.valid_until > utcnow(),
            DeviceCredentialRow.owner_id == owner_id,
            DeviceCredentialRow.revoked.is_(False),
        )
    )
    for account_grant in account_grants:
        try:
            await require_authority(session, owner_id, account_grant.agent_id, account_grant.id)
        except LonoraError:
            continue
        result.add(account_grant.agent_id)
    if not candidates:
        return result
    # Hold the owner roster/ancestors and joined grants/devices strongly in the
    # identity map. The existing authority validator can then be reused without
    # a new per-Agent or per-avatar query/permission implementation.
    agents = {
        row.id: row
        for row in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id))
    }
    for grant, goal, _device in candidates:
        agent = agents.get(goal.agent_id or "")
        if (
            agent is None
            or agent.paused
            or goal.agent_id != grant.agent_id
            or goal.state.get("super_bot_request_id") != grant.id
            or goal.state.get("status") not in {"active", "waiting", "blocked"}
        ):
            continue
        try:
            await require_goal_authority(session, goal, mode=grant.mode)
        except LonoraError:
            continue
        result.add(agent.id)
    return result
