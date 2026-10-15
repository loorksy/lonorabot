from lonora_contracts.trading import TradeRequest
from lonora_session.idempotency import request_hash


def trade_fingerprint(request: TradeRequest) -> str:
    payload = request.model_dump(mode="json")
    for flag in ("clear_stop_loss", "clear_take_profit"):
        if not payload[flag]:
            payload.pop(flag)
    if not payload.get("thesis_id"):
        payload.pop("thesis_id", None)
    return request_hash(payload)
