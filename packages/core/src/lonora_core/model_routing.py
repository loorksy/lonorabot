from lonora_contracts.model_routing import Capability, ModelSelection, RoutingPolicy

from .user_error import LonoraError


def select_model(policy: RoutingPolicy, capability: Capability) -> ModelSelection:
    selected = policy.routes.get(capability) if policy.mode == "custom" else policy.unified
    if selected is None and capability in {
        Capability.CONVERSATION,
        Capability.REASONING,
        Capability.RESEARCH,
        Capability.BACKGROUND,
    }:
        selected = policy.unified
    if selected is None:
        raise LonoraError("model_not_configured", 409)
    return selected
