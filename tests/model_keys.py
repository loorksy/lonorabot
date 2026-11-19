"""A model provider's key, saved as its Secret card saves it, for fixtures that need a
connected provider but do not test the card (tests/test_model_provider_card.py does)."""

from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_api.routes.secret_cards import save_model_key
from lonora_api.runtime import ApiRuntime


async def connect_model_key(runtime: ApiRuntime, owner_id: str, provider: str, key: str) -> None:
    store = EncryptedSecretStore(
        runtime.db, runtime.settings.encryption_key.get_secret_value(), owner_id
    )
    async with runtime.db.sessions() as session, session.begin():
        await save_model_key(session, store, provider, {"API_KEY": key})
