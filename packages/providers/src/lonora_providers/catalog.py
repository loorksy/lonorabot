from lonora_contracts.model_catalog import ModelDescriptor
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository


async def read_catalog(db: Database, provider: str) -> list[ModelDescriptor]:
    async with db.sessions() as session:
        payload = await SettingsRepository().get(session, "catalog:" + provider)
        return [ModelDescriptor.model_validate(item) for item in payload.get("models", [])]


async def store_catalog(db: Database, provider: str, models: list[ModelDescriptor]) -> None:
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session,
            "catalog:" + provider,
            {"models": [item.model_dump(mode="json") for item in models]},
        )
