from typing import Any

from lonora_contracts.domain import AgentCreate, AgentUpdate
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import assert_payload_binding, scope_data
from .schema import AgentRow, MemoryRow
from .transactions import owned_agent


def agent_data(row: AgentRow, *, super_bot_active: bool = False) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "title": row.title,
        "description": row.description,
        "avatar": row.avatar,
        "color": row.color,
        "instructions": row.instructions,
        "paused": row.paused,
        "super_bot_active": super_bot_active,
        "role": row.role,
        "execution_mode": row.execution_mode,
        "scope": scope_data(row),
        "trading_account_id": row.trading_account_id,
        "trading_symbol": row.trading_symbol,
        "parent_id": row.parent_id,
        "created_at": row.created_at.isoformat(),
    }


async def create_agent(
    session: AsyncSession,
    owner_id: str,
    request: AgentCreate,
    parent_id: str | None = None,
    agent_id: str | None = None,
) -> AgentRow:
    role = "specialist" if request.trading_account_id else "legacy"
    execution_mode = "live"
    if parent_id:
        parent = await owned_agent(session, owner_id, parent_id)
        execution_mode = parent.execution_mode
        if parent.role == "delegated" or not parent.trading_account_id:
            # Owner-wide visibility is not a financial scope a child can inherit.
            # Unbound legacy parents also cannot mint new unrestricted children.
            if request.trading_account_id is not None or request.trading_symbol is not None:
                from lonora_core.user_error import LonoraError

                raise LonoraError("delegated_financial_authority_forbidden", 403)
            role = "delegated"
        else:
            role = "specialist"
        if request.trading_account_id is not None:
            assert_payload_binding(
                parent, {"account_id": request.trading_account_id, "symbol": request.trading_symbol}
            )
        request = request.model_copy(
            update={
                "trading_account_id": parent.trading_account_id,
                "trading_symbol": parent.trading_symbol,
            }
        )
    row = AgentRow(
        owner_id=owner_id,
        parent_id=parent_id,
        role=role,
        execution_mode=execution_mode,
        **request.model_dump(),
    )
    if agent_id:
        row.id = agent_id
    session.add(row)
    await session.flush()
    session.add(MemoryRow(agent_id=row.id))
    return row


async def list_agents(session: AsyncSession, owner_id: str) -> list[AgentRow]:
    return list(
        (
            await session.scalars(
                select(AgentRow)
                .where(AgentRow.owner_id == owner_id)
                .order_by(
                    case((AgentRow.role == "personal", 0), else_=1),
                    AgentRow.created_at,
                    AgentRow.id,
                )
            )
        ).all()
    )


async def update_agent(
    session: AsyncSession, owner_id: str, agent_id: str, request: AgentUpdate
) -> AgentRow:
    row = await owned_agent(session, owner_id, agent_id, lock=True)
    for key, value in request.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    return row
