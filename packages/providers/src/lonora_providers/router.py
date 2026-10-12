from collections.abc import Awaitable, Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.model_routing import select_model
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository

from .credentials import ProviderCredentials
from .fallback import may_fallback
from .registry import model_adapter
from .routing_policy import read_policy


class GlobalModelRouter:
    def __init__(
        self,
        db: Database,
        credentials: ProviderCredentials,
        factory: Callable[[str, str], ModelAdapter] = model_adapter,
    ):
        self.db, self.credentials, self.factory = db, credentials, factory

    async def complete(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        on_attempt: Callable[[ModelSelection], Awaitable[None]] | None = None,
    ) -> tuple[ModelReply, ModelSelection]:
        choice = select_model(await read_policy(self.db), capability)
        async with self.db.sessions() as session:
            backups = await SettingsRepository().get(session, "model_backups")
        choices = [choice] + [
            ModelSelection.model_validate(item) for item in backups.get("choices", [])
        ]
        failure: LonoraError | None = None
        for selection in choices:
            adapter = self.factory(
                selection.provider, await self.credentials.resolve(selection.provider)
            )
            try:
                if on_attempt:
                    await on_attempt(selection)
                return await adapter.complete(
                    selection.model, messages, tools, on_delta=on_delta
                ), selection
            except LonoraError as error:
                failure = error
                if not may_fallback(error):
                    raise
            finally:
                await adapter.close()
        raise failure or LonoraError("model_provider_unavailable", 502)
