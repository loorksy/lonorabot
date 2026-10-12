from lonora_contracts.model_catalog import ModelDescriptor
from lonora_db.client import Database

from .catalog import store_catalog
from .credentials import ProviderCredentials
from .registry import model_adapter


async def discover_models(
    db: Database, credentials: ProviderCredentials, provider: str
) -> list[ModelDescriptor]:
    adapter = model_adapter(provider, await credentials.resolve(provider))
    try:
        models = await adapter.discover()
    finally:
        await adapter.close()
    await store_catalog(db, provider, models)
    return models
