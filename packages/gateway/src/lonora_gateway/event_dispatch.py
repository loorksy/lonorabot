from lonora_bus.runtime_events import RuntimeEvents
from lonora_contracts.events import EventEnvelope


def dispatch_event(bus: RuntimeEvents, event: EventEnvelope) -> None:
    bus.publish(event)
