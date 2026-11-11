"""What earlier reads learned about the symbols of the agent's accounts.

Server-written from single matches the broker confirmed (``symbols.remember_resolution``),
kept with the connection and shown before the first call, so an instrument is named the
way the account lists it without a failed call first. An order still names a symbol the
live catalogue lists exactly; this text only informs.
"""

from lonora_db.broker_sessions import (
    BrokerSessionRepository,
    account_symbols,
    current_broker_identity,
)
from lonora_db.schema import AgentRow
from sqlalchemy.ext.asyncio import AsyncSession

ACCOUNTS = 10
ENTRIES = 20
NOTE = (
    "Names an earlier read resolved on each account, as its broker confirmed them then. "
    "Use the symbol in reads. Before an order on one of these words, read it once by the "
    "owner's word: what an account lists can change."
)


async def account_symbols_context(session: AsyncSession, owner_id: str, agent: AgentRow) -> str:
    """The section body, or nothing when no account has learned a symbol yet."""
    lines: list[str] = []
    for row in (await BrokerSessionRepository().list(session, owner_id))[:ACCOUNTS]:
        if agent.trading_account_id and row.id != agent.trading_account_id:
            # A fixed or focused agent is shown its own account only.
            continue
        newest = sorted(
            account_symbols(row).items(), key=lambda item: str(item[1].get("at", "")), reverse=True
        )
        if not newest:
            continue
        broker = str((current_broker_identity(row) or {}).get("broker") or "").strip()
        known = "; ".join(f"{word} = {entry['symbol']}" for word, entry in newest[:ENTRIES])
        lines.append(f"account {row.id}{' (' + broker + ')' if broker else ''}: {known}")
    return "\n".join([NOTE, *lines]) if lines else ""
