from typing import Any

from lonora_contracts.trading import TradeRequest
from lonora_session.idempotency import request_hash, stable_id

from .base import Tool
from .context import ToolContext


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    args.pop("operation_id", None)
    args["operation_id"] = stable_id(context.lease.run_id, "trade:" + request_hash(args))
    request = TradeRequest.model_validate(args)
    return (await context.trading.execute(context.owner_id, request, context.lease)).model_dump(
        mode="json"
    )


def tools() -> list[Tool]:
    return [
        Tool(
            "trade_execute",
            "Execute a structured broker operation only when global Trading ON allows it. Identical operations within one run are deduplicated; ambiguous results are reconciled without blind resend.",
            TradeRequest,
            execute,
        )
    ]
