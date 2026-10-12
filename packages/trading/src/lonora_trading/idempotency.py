from lonora_contracts.trading import TradeRequest
from lonora_session.idempotency import request_hash


def trade_fingerprint(request: TradeRequest) -> str:
    return request_hash(request.model_dump(mode="json"))
