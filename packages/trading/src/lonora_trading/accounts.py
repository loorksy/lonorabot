from typing import Any

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.account import AccountState


async def account_snapshot(
    broker: BrokerAdapter, account: AccountState | None = None
) -> dict[str, Any]:
    account = account or await broker.account()
    positions, orders = await broker.positions(), await broker.orders()
    return {
        "account": account.model_dump(mode="json"),
        "positions": [p.model_dump(mode="json") for p in positions],
        "orders": [o.model_dump(mode="json") for o in orders],
    }
