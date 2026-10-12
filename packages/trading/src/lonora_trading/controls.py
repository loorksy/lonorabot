from lonora_contracts.trading import TradingControl
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository


async def read_controls(db: Database) -> TradingControl:
    async with db.sessions() as session:
        return TradingControl.model_validate(
            await SettingsRepository().get(session, "trading_control")
        )


async def save_controls(db: Database, controls: TradingControl) -> TradingControl:
    if controls.emergency_stop:
        controls.enabled = False
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "trading_control", controls.model_dump())
    return controls
