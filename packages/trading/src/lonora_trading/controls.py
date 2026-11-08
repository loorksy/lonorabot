from lonora_contracts.domain import new_id
from lonora_contracts.trading import TradingControl
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.owner import get_owner
from lonora_db.transactions import SettingsRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def read_controls(db: Database) -> TradingControl:
    async with db.sessions() as session:
        return TradingControl.model_validate(
            await SettingsRepository().get(session, "trading_control")
        )


async def save_controls(db: Database, controls: TradingControl) -> TradingControl:
    async with db.sessions() as session, session.begin():
        return await apply_controls(session, controls)


async def apply_controls(session: AsyncSession, controls: TradingControl) -> TradingControl:
    """Store the owner's Stop/Resume inside the caller's transaction (owner session only)."""
    if controls.emergency_stop:
        controls.enabled = False
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(1524053102)"))
    previous = TradingControl.model_validate(
        await SettingsRepository().get(session, "trading_control")
    )
    if previous == controls:
        # Repeating the current state is not a change: "stopped since" stays true.
        return controls
    await SettingsRepository().put(session, "trading_control", controls.model_dump())
    owner = await get_owner(session)
    if owner:
        emit(
            session,
            owner.id,
            "trading.controls_updated",
            payload={**controls.model_dump(), "transition_id": new_id()},
        )
    return controls
