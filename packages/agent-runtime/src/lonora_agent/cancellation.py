from lonora_db.runs import require_lease
from lonora_tools.context import ToolContext


async def cancellation_checkpoint(context: ToolContext) -> None:
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
