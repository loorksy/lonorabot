from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.model_routing import select_model
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_providers.routing_policy import read_policy


async def voice_routes(db: Database) -> tuple[ModelSelection, ModelSelection]:
    policy = await read_policy(db)
    stt, tts = select_model(policy, Capability.STT), select_model(policy, Capability.TTS)
    if stt.provider != "openai" or tts.provider != "openai":
        raise LonoraError("voice_provider_unsupported", 409)
    return stt, tts


async def live_model(db: Database) -> ModelSelection:
    policy = await read_policy(db)
    selected = policy.routes.get(Capability.REALTIME_VOICE)
    if selected is None:
        return ModelSelection(provider="openai", model="gpt-live-1")
    if selected.provider != "openai" or selected.model not in {"gpt-live-1", "gpt-live-1-mini"}:
        raise LonoraError("voice_model_unsupported", 409)
    return selected
