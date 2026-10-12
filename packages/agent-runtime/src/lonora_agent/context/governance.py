from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError


def govern_context(messages: list[ModelMessage], maximum_chars: int = 120000) -> list[ModelMessage]:
    if not messages:
        raise LonoraError("empty_model_context", 500)
    system = [message for message in messages if message.role == "system"]
    history = [message for message in messages if message.role != "system"]
    budget = maximum_chars - sum(len(message.content) for message in system)
    retained: list[ModelMessage] = []
    for message in reversed(history):
        if len(message.content) > budget:
            break
        retained.append(message)
        budget -= len(message.content)
    if history and not retained:
        raise LonoraError("context_limit_exceeded", 413)
    return system + list(reversed(retained))
