from collections.abc import Awaitable, Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_context import ModelContextPolicy
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.model_routing import select_model
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository

from .context import prepare_context
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
            settings = SettingsRepository()
            backups = await settings.get(session, "model_backups")
            policy = ModelContextPolicy.model_validate(await settings.get(session, "model_context"))
            choices = [choice] + [
                ModelSelection.model_validate(item) for item in backups.get("choices", [])
            ]
            catalogs: dict[str, list[ModelDescriptor]] = {}
            for provider in dict.fromkeys(item.provider for item in choices):
                payload = await settings.get(session, "catalog:" + provider)
                catalogs[provider] = [
                    ModelDescriptor.model_validate(item) for item in payload.get("models", [])
                ]
        failure: LonoraError | None = None
        for selection in choices:
            descriptor = next(
                (
                    item
                    for item in catalogs[selection.provider]
                    if item.id == selection.model and item.provider == selection.provider
                ),
                None,
            )
            # Rebuild from the original working messages for EVERY attempt, including fallback.
            prepared = prepare_context(
                messages,
                tools,
                descriptor,
                policy,
                provider=selection.provider,
                model=selection.model,
            )
            adapter = self.factory(
                selection.provider, await self.credentials.resolve(selection.provider)
            )
            try:
                if on_attempt:
                    await on_attempt(selection)
                reply = await adapter.complete(
                    selection.model,
                    prepared.messages,
                    tools,
                    max_output_tokens=prepared.output_tokens,
                    on_delta=on_delta,
                )
                reply.provider_metadata["context_budget"] = {
                    **prepared.diagnostics,
                    "actual_input_tokens": reply.usage.input_tokens or None,
                    "actual_output_tokens": reply.usage.output_tokens or None,
                }
                return reply, selection
            except LonoraError as error:
                failure = error
                if not may_fallback(error):
                    raise
            finally:
                await adapter.close()
        raise failure or LonoraError("model_provider_unavailable", 502)
