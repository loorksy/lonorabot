from lonora_contracts.domain import new_id
from lonora_contracts.trading import TradingControl
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.owner import get_owner
from lonora_db.transactions import SettingsRepository
from sqlalchemy import text


async def read_controls(db: Database) -> TradingControl:
    async with db.sessions() as session:
        return TradingControl.model_validate(
            await SettingsRepository().get(session, "trading_control")
        )


async def save_controls(db: Database, controls: TradingControl) -> TradingControl:
    if controls.emergency_stop:
        controls.enabled = False
    async with db.sessions() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(1524053102)"))
        previous = TradingControl.model_validate(
            await SettingsRepository().get(session, "trading_control")
        )
        await SettingsRepository().put(session, "trading_control", controls.model_dump())
        owner = await get_owner(session)
        if owner and previous != controls:
            emit(
                session,
                owner.id,
                "trading.controls_updated",
                payload={**controls.model_dump(), "transition_id": new_id()},
            )
    return controls
