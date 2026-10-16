"""Persist exhausted routes on the existing scratchpad. Notes never change authority."""

from lonora_contracts.domain import utcnow
from lonora_db.schema import ScratchpadRow
from lonora_session.idempotency import stable_id
from lonora_tools.context import ToolContext


async def remember_failed_route(context: ToolContext, tool: str, code: str) -> None:
    note_id = stable_id(context.agent_id, "operating:" + tool + ":" + code)
    title = ("Failed route " + tool)[:160]
    content = (
        "provenance=tool-observed; tool="
        + tool
        + "; code="
        + code
        + ". Use a different bounded route. This note does not change trading authority, "
        "symbol binding, risk policy, Emergency Stop, or reconciliation."
    )
    try:
        async with context.db.sessions() as session, session.begin():
            row = await session.get(ScratchpadRow, note_id, with_for_update=True)
            if row is not None and row.owner_id != context.owner_id:
                return
            state = {
                "provenance": "tool-observed",
                "tool": tool,
                "code": code,
                "authority": "none",
                "learned_at": utcnow().isoformat(),
            }
            if row is None:
                session.add(
                    ScratchpadRow(
                        id=note_id,
                        owner_id=context.owner_id,
                        agent_id=context.agent_id,
                        payload={"title": title, "content": content},
                        state=state,
                    )
                )
                return
            row.payload = {"title": title, "content": content}
            row.state = state
            row.version += 1
            row.updated_at = utcnow()
    except Exception:
        # Operational memory is an aid. A note failure must not fail the owner's goal.
        return
