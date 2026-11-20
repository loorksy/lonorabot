"""Read-only presentation of agents trading on their own, never an execution grant."""

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AccountAuthorityRow, AgentRow, DeviceCredentialRow


async def agents_on_their_own(session: AsyncSession, owner_id: str) -> set[str]:
    """Agents that are not paused and either are in Full (mandate 4.1) or hold at least one
    signed grant in force right now (until grants are deleted).

    The avatar marker reads this, and so does the automatic retry of a late instruction
    (``run_retry``); enforcement re-reads the mode and the grant at every send.
    """
    from .account_authority import require_authority
    from .agent_permissions import permission_record

    result: set[str] = set()
    account_grants = await session.scalars(
        select(AccountAuthorityRow)
        .join(DeviceCredentialRow, DeviceCredentialRow.id == AccountAuthorityRow.device_id)
        .join(AgentRow, AgentRow.id == AccountAuthorityRow.agent_id)
        .where(
            AgentRow.owner_id == owner_id,
            AgentRow.paused.is_(False),
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.status == "active",
            AccountAuthorityRow.valid_until.is_(None)
            | (AccountAuthorityRow.valid_until > utcnow()),
            DeviceCredentialRow.owner_id == owner_id,
            DeviceCredentialRow.revoked.is_(False),
        )
    )
    for account_grant in account_grants:
        if account_grant.agent_id in result:
            continue
        try:
            await require_authority(session, owner_id, account_grant.agent_id, account_grant.id)
        except LonoraError:
            continue
        result.add(account_grant.agent_id)
    full = await session.scalars(
        select(AgentRow.id).where(
            AgentRow.owner_id == owner_id,
            AgentRow.paused.is_(False),
            AgentRow.trading_mode == "full",
        )
    )
    for agent_id in list(full):
        if agent_id in result:
            continue
        # The ladder's "No trading" still refuses every send before the door reads the mode
        # (``agent_analysis_only``), so such an agent does not trade on its own, as its
        # status line says (``trading_readiness``).
        try:
            record = await permission_record(session, owner_id, agent_id)
        except LonoraError:
            continue
        if record.fallback_level != "analysis":
            result.add(agent_id)
    return result
