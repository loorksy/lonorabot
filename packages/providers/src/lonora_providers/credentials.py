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

    async def connection(self, provider: str) -> tuple[str, str | None]:
        """The provider's key and, for a provider with an owner endpoint, the base URL that
        key belongs to, from one read, so a card saved meanwhile never pairs one card's
        key with another's URL. The card's URL goes with the card's key; the deployment's
        URL with the deployment's or a settings-era key. A URL that fails the check
        connects nothing: the router passes over the provider as unconfigured instead of
        failing every route that lists it."""
        if provider not in OWNER_ENDPOINT:
            return await self.resolve(provider), None
        async with self.db.sessions() as session:
            saved = await saved_key(session, provider)
        prefix = "LONORA_" + provider.upper()
        if saved is not None:
            key: str | None = await self.store.read(saved.secret_id)
            url = saved.url or _deployment(prefix + "_BASE_URL")
        else:
            key, url = _deployment(prefix + "_API_KEY"), _deployment(prefix + "_BASE_URL")
        if not key or not url:
            # A key without the URL it belongs to connects nothing, nor the reverse.
            raise LonoraError("model_not_configured", 409)
        try:
            return key, compatible_endpoint(url)
        except LonoraError:
            log.warning("model_endpoint_unsafe provider=%s", provider)
            raise LonoraError("model_not_configured", 409) from None

    async def resolve(self, provider: str) -> str:
        if provider in OWNER_ENDPOINT:
            return (await self.connection(provider))[0]
        async with self.db.sessions() as session:
            saved = await saved_key(session, provider)
        if saved is not None:
            return await self.store.read(saved.secret_id)
        value = _deployment("LONORA_" + provider.upper() + "_API_KEY")
        if value:
            return value
        raise LonoraError("model_not_configured", 409)

    async def endpoint(self, provider: str) -> str | None:
        """The base URL of a provider with an owner endpoint, with its key; else None."""
        if provider not in OWNER_ENDPOINT:
            return None
        try:
            return (await self.connection(provider))[1]
        except LonoraError:
            return None

    async def configured(self, provider: str) -> bool:
        try:
            await self.resolve(provider)
            return True
        except LonoraError:
            return False
