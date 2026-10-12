from lonora_contracts.events import EventEnvelope


def runtime_event(
    kind: str, run_id: str, thread_id: str, payload: dict[str, object]
) -> EventEnvelope:
    return EventEnvelope(kind=kind, run_id=run_id, thread_id=thread_id, payload=payload)
