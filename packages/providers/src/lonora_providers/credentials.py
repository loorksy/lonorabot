import os

from dotenv import dotenv_values
from lonora_adapter_kit.secrets import SecretStore
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.model_credentials import credential_id


class ProviderCredentials:
    def __init__(self, db: Database, store: SecretStore):
        self.db, self.store = db, store

    async def resolve(self, provider: str) -> str:
        async with self.db.sessions() as session:
            secret_id = await credential_id(session, provider)
        if secret_id:
            return await self.store.read(secret_id)
        name = "LONORA_" + provider.upper() + "_API_KEY"
        value = os.environ.get(name) or dotenv_values(".env").get(name)
        if value:
            return value
        raise LonoraError("model_not_configured", 409)

    async def configured(self, provider: str) -> bool:
        try:
            await self.resolve(provider)
            return True
        except LonoraError:
            return False
