from lonora_contracts.events import EventEnvelope


def channel_projection(event: EventEnvelope) -> str | None:
    if event.kind != "message.created":
        return None
    if event.payload.get("role") != "assistant":
        return None
    content = event.payload.get("content")
    return content if isinstance(content, str) else None
