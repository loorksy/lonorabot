import os

from lonora_gateway.process_identity import process_identity


def worker_identity() -> dict[str, object]:
    return {"id": process_identity(), "pid": os.getpid()}
