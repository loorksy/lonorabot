"""«سجل الإجراءات»: owner-visible actions projected from durable events (Q45).

Every entry comes from one row of ``ln_events``; nothing is synthesised. The projection
keeps only actions the owner would recognise (an agent created, authority or limits
changed, a restriction set or lifted, an approval decided, an operation resolved, a
task created or finished, a skill saved, supervision granted or revoked, a watch
triggered, a goal or knowledge entry added) and names them with a stable ``code`` that
the clients label. The subject is the agent's name, or the task's or skill's own name.
"""

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, EventRow, SkillRow, TicketRow

DIRECT: dict[str, str] = {
    "agent.created": "agent_created",
    "account_authority.updated": "authority_changed",
    "trading.execution_policy_updated": "limits_changed",
    "trading.restriction_created": "restriction_set",
    "trading.restriction_revoked": "restriction_lifted",
    "trading.operation_resolved": "operation_resolved",
    "task.created": "task_created",
    "skills.created": "skill_created",
    "skills.updated": "skill_updated",
    "supervision.granted": "supervision_granted",
    "supervision.revoked": "supervision_revoked",
    "watch.confirmed": "watch_triggered",
    "agent_goals.created": "goal_created",
    "knowledge_links.created": "knowledge_added",
}
TASK_STATUS = {"completed": "task_completed", "cancelled": "task_cancelled"}
APPROVAL_STATUS = {"approved": "approval_approved", "rejected": "approval_rejected"}
KINDS = [*DIRECT, "task.updated", "trading.approval.updated"]


def activity_code(event: EventRow) -> str | None:
    if event.kind in DIRECT:
        return DIRECT[event.kind]
    status = str(event.payload.get("status", ""))
    if event.kind == "task.updated":
        return TASK_STATUS.get(status)
    if event.kind == "trading.approval.updated":
        return APPROVAL_STATUS.get(status)
    return None


def skill_title(payload: dict[str, Any]) -> str:
    manifest = cast(dict[str, Any], payload.get("manifest") or {})
    return str(manifest.get("title") or payload.get("name", ""))


async def activity(
    session: AsyncSession, owner_id: str, *, limit: int = 50, before: int | None = None
) -> dict[str, Any]:
    entries: list[tuple[EventRow, str]] = []
    cursor = before
    seen_tasks: set[tuple[str, str]] = set()
    # Status events repeat (every save of a Task emits one); scan in pages until full.
    for _ in range(8):
        query = select(EventRow).where(EventRow.owner_id == owner_id, EventRow.kind.in_(KINDS))
        if cursor is not None:
            query = query.where(EventRow.cursor < cursor)
        page = list(
            (await session.scalars(query.order_by(EventRow.cursor.desc()).limit(200))).all()
        )
        for event in page:
            code = activity_code(event)
            if code is None:
                continue
            if code.startswith("task_") and event.kind == "task.updated":
                identity = (str(event.payload.get("id")), code)
                if identity in seen_tasks:
                    continue
                seen_tasks.add(identity)
            entries.append((event, code))
            if len(entries) >= limit:
                break
        if len(entries) >= limit or len(page) < 200:
            break
        cursor = page[-1].cursor
    agent_ids = {event.agent_id for event, _ in entries if event.agent_id}
    task_ids = {str(event.payload.get("id")) for event, code in entries if code.startswith("task_")}
    skill_ids = {
        str(event.payload.get("id")) for event, code in entries if code.startswith("skill_")
    }
    agents = (
        {
            row.id: row.name
            for row in await session.scalars(select(AgentRow).where(AgentRow.id.in_(agent_ids)))
        }
        if agent_ids
        else {}
    )
    tasks = (
        {
            row.id: str(row.payload.get("title", ""))
            for row in await session.scalars(
                select(TicketRow).where(TicketRow.owner_id == owner_id, TicketRow.id.in_(task_ids))
            )
        }
        if task_ids
        else {}
    )
    skills = (
        {
            row.id: skill_title(row.payload)
            for row in await session.scalars(
                select(SkillRow).where(SkillRow.owner_id == owner_id, SkillRow.id.in_(skill_ids))
            )
        }
        if skill_ids
        else {}
    )
    items: list[dict[str, Any]] = []
    for event, code in entries:
        reference = str(event.payload.get("id", ""))
        subject = (
            tasks.get(reference, "")
            if code.startswith("task_")
            else skills.get(reference, "")
            if code.startswith("skill_")
            else agents.get(event.agent_id or "", "")
        )
        items.append(
            {
                "id": str(event.cursor),
                "code": code,
                "agent_id": event.agent_id,
                "thread_id": event.thread_id,
                "subject": subject,
                "created_at": event.created_at.isoformat(),
            }
        )
    return {
        "items": items,
        "next_before": int(items[-1]["id"]) if len(items) >= limit else None,
    }
