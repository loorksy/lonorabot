"""Seed the domain pages (UI phase 4b) with the reference's own demo rows.

Run by tests/ui-reference/domain-states.mjs after seed_reference.py. Reads one JSON object
on stdin, ``{"agents": {...}, "threads": {...}}`` (the init answer), and prints the ids it
made. Everything goes through the owner API, except what has no owner route: the agent's
alert (an attention row an agent raises) and the semantic note (its embedding needs a
provider), which are written as rows. Running it again on the same database adds nothing.

The reference's ``initial``: task «متابعة الذهب» (gold), goal «متابعة السوق», schedule
«موجز الصباح» (Lonora, daily 09:00), skill «موجز الأخبار», knowledge «دليل العمل», file
«دليل_التجربة.txt», and the notification «موجز الصباح جاهز». Gold trades, so its goals
are trading plans (Q41); the light goal is seeded on the research agent instead.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_streaming import Fixture  # noqa: E402
from lonora_contracts.domain import utcnow  # noqa: E402
from lonora_db.schema import AttentionRow, SemanticMemoryRow  # noqa: E402
from sqlalchemy import select  # noqa: E402

FILE_TEXT = "هذا نموذج محلي لواجهات Lonora.\nالاتصالات والمكالمات والتداول محاكاة."


async def listing(fixture: Fixture, path: str) -> list[dict[str, Any]]:
    response = await fixture.client.get("/api" + path)
    assert response.is_success, f"GET {path}: HTTP {response.status_code}"
    return response.json()


async def seed(fixture: Fixture, agents: dict[str, str], threads: dict[str, str]) -> dict[str, Any]:
    lonora, gold, research = agents["lonora"], agents["gold"], agents["research"]
    tasks = [row for row in await listing(fixture, "/tasks") if row["title"] == "متابعة الذهب"]
    task = (
        tasks[0]
        if tasks
        else await fixture.request(
            "POST",
            f"/tasks?agent_id={gold}&thread_id={threads['gold']}",
            {
                "title": "متابعة الذهب",
                "description": "متابعة السوق وإعداد ملخص بالمستجدات.",
                "due_at": utcnow().replace(hour=18, minute=0, second=0, microsecond=0).isoformat(),
                "completion_criteria": "ملخص مع المصادر",
            },
        )
    )
    if not await listing(fixture, f"/agent-goals?agent_id={research}"):
        await fixture.request(
            "POST",
            "/agent-goals",
            {
                "agent_id": research,
                "payload": {"title": "متابعة السوق", "description": "تنبيه عند وجود مستجدات مهمة"},
            },
        )
    if not await listing(fixture, f"/routines?agent_id={lonora}"):
        await fixture.request(
            "POST",
            f"/routines/{lonora}",
            {"title": "موجز الصباح", "prompt": "موجز الصباح", "cron": "0 9 * * *"},
        )
    skills = await listing(fixture, f"/skills?agent_id={lonora}")
    skill = (
        skills[0]
        if skills
        else await fixture.request(
            "POST",
            "/skills",
            {
                "agent_id": lonora,
                "payload": {
                    "name": "news-brief",
                    "content": "اجمع الأخبار من المصادر المحددة ثم اكتب موجزًا مع الروابط.",
                    "enabled": True,
                    "manifest": {
                        "id": "news-brief",
                        "version": "1.0.0",
                        "title": "موجز الأخبار",
                        "description": "تلخيص الأخبار مع المصادر",
                        "required_tools": ["web_search"],
                    },
                },
            },
        )
    )
    files = await listing(fixture, f"/artifacts?agent_id={lonora}")
    if not files:
        response = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("دليل_التجربة.txt", FILE_TEXT.encode(), "text/plain")},
            data={"agent_id": lonora},
        )
        assert response.is_success, response.text
    async with fixture.runtime.db.sessions() as session, session.begin():
        note_id = "reference-note-" + lonora[:20]
        if await session.get(SemanticMemoryRow, note_id) is None:
            session.add(
                SemanticMemoryRow(
                    id=note_id,
                    owner_id=fixture.owner,
                    agent_id=lonora,
                    payload={
                        "title": "دليل العمل",
                        "text": "اكتب ملخصات واضحة واذكر المصادر.",
                        "embedding": [],
                        "model": "reference-seed",
                    },
                )
            )
        key = "reference-brief-" + lonora[:16]
        found = await session.scalar(
            select(AttentionRow).where(
                AttentionRow.owner_id == fixture.owner, AttentionRow.logical_key == key
            )
        )
        if found is None:
            session.add(
                AttentionRow(
                    owner_id=fixture.owner,
                    agent_id=lonora,
                    thread_id=threads["lonora"],
                    logical_key=key,
                    coalesce_key=key,
                    importance="informational",
                    code="agent_notification",
                    parameters={
                        "summary": "أعدّ Lonora موجز اليوم: لا مستجدات عاجلة. افتح محادثته لقراءته.",
                        "delivery": "in_app",
                    },
                    due_at=utcnow(),
                )
            )
    return {"task": task["id"], "skill": skill["id"]}


async def main(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        return await seed(fixture, data["agents"], data["threads"])
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(json.load(sys.stdin)))))
