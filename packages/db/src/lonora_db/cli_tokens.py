"""Each agent's own `lonora` CLI token (mandate 7.3.3).

Each agent gets one token the first time ``cli_token`` is asked for it. The CLI endpoint
maps a presented token to exactly one agent; deleting the agent deletes its row
(``ON DELETE CASCADE``), which revokes it.
"""

import hashlib
import secrets

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentCliTokenRow, AgentRow

# 32 random bytes; the prefix only makes a leaked token recognizable in a scan.
TOKEN_PREFIX = "lnr_"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def cli_token(session: AsyncSession, key: str, owner_id: str, agent_id: str) -> str:
    """The agent's token, issued on first use. The same value every time, so commands
    started earlier (background processes included) keep working."""
    row = await session.get(AgentCliTokenRow, agent_id)
    cipher = SecretCipher(key)
    if row is not None and row.owner_id == owner_id:
        return cipher.decrypt(row.ciphertext)
    agent = await session.get(AgentRow, agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    # Two commands starting at once for a new agent: one insert wins, both read it back.
    await session.execute(
        insert(AgentCliTokenRow)
        .values(
            agent_id=agent_id,
            owner_id=owner_id,
            token_hash=token_hash(token),
            ciphertext=cipher.encrypt(token),
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["agent_id"])
    )
    row = await session.get(AgentCliTokenRow, agent_id, populate_existing=True)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    return cipher.decrypt(row.ciphertext)


async def revoke_cli_token(session: AsyncSession, agent_id: str) -> None:
    """Revoke the agent's token explicitly. Deleting the agent row revokes it by cascade."""
    await session.execute(delete(AgentCliTokenRow).where(AgentCliTokenRow.agent_id == agent_id))


async def agent_for_cli_token(session: AsyncSession, token: str) -> AgentRow | None:
    """The one agent a token names, or None for any token Lonora did not issue."""
    if not token.startswith(TOKEN_PREFIX) or len(token) > 128:
        return None
    return await session.scalar(
        select(AgentRow)
        .join(AgentCliTokenRow, AgentCliTokenRow.agent_id == AgentRow.id)
        .where(
            AgentCliTokenRow.token_hash == token_hash(token),
            AgentCliTokenRow.owner_id == AgentRow.owner_id,
        )
    )


async def owner_cli_tokens(session: AsyncSession, key: str, owner_id: str) -> list[str]:
    """Every token issued to the owner's agents, for the scan of workspace output: a
    command that prints its token returns [secret:LONORA_AGENT_TOKEN]."""
    cipher = SecretCipher(key)
    rows = await session.scalars(
        select(AgentCliTokenRow.ciphertext).where(AgentCliTokenRow.owner_id == owner_id)
    )
    return [cipher.decrypt(row) for row in rows]
