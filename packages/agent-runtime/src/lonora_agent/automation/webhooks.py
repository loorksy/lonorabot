from typing import Any

from lonora_contracts.runs import RunRequest
from lonora_db.client import Database
from lonora_db.runs import create_run, run_data
from lonora_db.schema import EffectReceiptRow
from lonora_session.idempotency import stable_id


async def webhook_wake(
    db: Database, owner_id: str, request: RunRequest, nonce: str
) -> dict[str, Any]:
    key = "webhook:" + stable_id(owner_id, nonce)
    async with db.sessions() as session, session.begin():
        receipt = await session.get(EffectReceiptRow, key)
        if receipt:
            return receipt.result
        request.trigger = "webhook"
        result = run_data(await create_run(session, owner_id, request))
        session.add(EffectReceiptRow(key=key, result=result))
        return result
