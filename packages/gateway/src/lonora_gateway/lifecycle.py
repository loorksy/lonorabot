from enum import StrEnum


class GatewayState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"
