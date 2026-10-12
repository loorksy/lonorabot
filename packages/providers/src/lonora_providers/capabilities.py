from lonora_contracts.model_catalog import ModelDescriptor


def supports(model: ModelDescriptor, capability: str) -> bool | None:
    if not model.verified:
        return None
    return capability in model.capabilities
