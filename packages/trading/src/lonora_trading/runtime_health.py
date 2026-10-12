from typing import Any

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_core.user_error import LonoraError


async def broker_health(broker: BrokerAdapter) -> dict[str, Any]:
    try:
        account = await broker.account()
        return {
            "ready": True,
            "account_id": account.id,
            "observed_at": account.observed_at.isoformat(),
        }
    except LonoraError as error:
        return {"ready": False, "code": error.code}
