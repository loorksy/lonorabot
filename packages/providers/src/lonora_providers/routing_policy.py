from lonora_contracts.model_routing import RoutingPolicy
from lonora_db.client import Database
from lonora_db.schema import SettingRow
from lonora_db.transactions import SettingsRepository

# The unified model Lonora chose (``default_model``), while the owner has saved no routing.
CHOSEN_BY_LONORA = "model_routing_chosen_by_lonora"


async def read_policy(db: Database) -> RoutingPolicy:
    async with db.sessions() as session:
        return RoutingPolicy.model_validate(
            await SettingsRepository().get(session, "model_routing")
        )


async def save_policy(db: Database, policy: RoutingPolicy) -> None:
    """The owner's routing: from now on theirs, never Lonora's choice (``default_model``)."""
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "model_routing", policy.model_dump(mode="json"))
        chosen = await session.get(SettingRow, CHOSEN_BY_LONORA)
        if chosen is not None:
            await session.delete(chosen)
