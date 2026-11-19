from typing import Any

from lonora_contracts.trading import TradeRequest
from lonora_session.idempotency import request_hash, stable_id


def trade_fingerprint(request: TradeRequest) -> str:
    payload = request.model_dump(mode="json")
    for flag in ("clear_stop_loss", "clear_take_profit"):
        if not payload[flag]:
            payload.pop(flag)
    if not payload.get("thesis_id"):
        payload.pop("thesis_id", None)
    return request_hash(payload)


def operation_id(run_id: str, agent_id: str, args: dict[str, Any], key: str | None) -> str:
    """The server-derived operation id (6.2). Without ``key`` it is the run's id for this
    exact request, so a repeat in the same run is the same operation and an unknown
    outcome is never resent. With ``key`` it is the calling agent's and the key's: the
    same key is the same operation in any run, and a new key names an intentional second
    identical order (the CLI's ``--key``, 7.3.5)."""
    if key is not None:
        return stable_id(agent_id, "key:" + key)
    return stable_id(run_id, "trade:" + request_hash(args))
