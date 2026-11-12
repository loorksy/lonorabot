import logging
import os

from dotenv import dotenv_values
from lonora_adapter_kit.secrets import SecretStore
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.model_credentials import saved_key
from lonora_security.network import compatible_endpoint

from .registry import OWNER_ENDPOINT

log = logging.getLogger("lonora.model_router")


def _deployment(name: str) -> str | None:
    return os.environ.get(name) or dotenv_values(".env").get(name) or None


class ProviderCredentials:
    def __init__(self, db: Database, store: SecretStore):
        self.db, self.store = db, store

    async def resolve(self, provider: str) -> str:
        if provider in OWNER_ENDPOINT and await self.endpoint(provider) is None:
            # A key without the URL it belongs to connects nothing.
            raise LonoraError("model_not_configured", 409)
        async with self.db.sessions() as session:
            saved = await saved_key(session, provider)
        if saved is not None:
            return await self.store.read(saved.secret_id)
        value = _deployment("LONORA_" + provider.upper() + "_API_KEY")
        if value:
            return value
        raise LonoraError("model_not_configured", 409)

    async def endpoint(self, provider: str) -> str | None:
        """The owner's base URL for a provider that has one, else ``None``. It travels
        with its key: the URL saved on the card when the card's key is the one in use,
        else the deployment's (with the deployment's or a settings-era key).

        A URL that fails the check connects nothing, so the router passes over the
        provider as unconfigured instead of failing every route that lists it.
        """
        if provider not in OWNER_ENDPOINT:
            return None
        async with self.db.sessions() as session:
            saved = await saved_key(session, provider)
        value = (saved.url if saved is not None else None) or _deployment(
            "LONORA_" + provider.upper() + "_BASE_URL"
        )
        if not value:
            return None
        try:
            return compatible_endpoint(value)
        except LonoraError:
            log.warning("model_endpoint_unsafe provider=%s", provider)
            return None

    async def configured(self, provider: str) -> bool:
        try:
            await self.resolve(provider)
            return True
        except LonoraError:
            return False
