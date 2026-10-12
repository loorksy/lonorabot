from lonora_contracts.model_routing import RoutingPolicy
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository


async def read_policy(db: Database) -> RoutingPolicy:
    async with db.sessions() as session:
        return RoutingPolicy.model_validate(
            await SettingsRepository().get(session, "model_routing")
        )


async def save_policy(db: Database, policy: RoutingPolicy) -> None:
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "model_routing", policy.model_dump(mode="json"))
