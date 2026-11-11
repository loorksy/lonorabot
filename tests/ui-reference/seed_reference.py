"""Seed the app with the reference's own demo data (docs/ui-reference/Lonora-Desktop-37.html,
``initial``) for tests/ui-reference/side-by-side.mjs.

Everything the owner can create goes through the API (in-process, the same routes the web
calls): onboarding and sign-in, a simulation broker account with XAUUSD, the three agents from
their templates, the group with its purpose and lead, the conversations and the read cursors.
Agent-authored messages have no owner route (a run writes them), so they are written into
history exactly as tests/chat_lists_browser.py does, at the reference's times (UTC).

Reads one JSON object on stdin and prints one JSON object:
``{"action": "init"}`` → cookies, agent and thread ids (on a database it seeded before, the same
ids with a fresh sign-in, so a run can be repeated with --no-bindings).
"""

import asyncio
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_streaming import Fixture  # noqa: E402
from lonora_db.messages import message_data  # noqa: E402
from lonora_db.schema import MessageReactionRow, MessageRow, RunRow, ThreadRow  # noqa: E402


def at(hour: int, minute: int) -> datetime:
    return datetime.now(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)


async def say(fixture: Fixture, thread_id: str, agent_id: str, content: str, when: datetime):
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        row = MessageRow(
            thread_id=thread_id,
            seq=thread.next_seq,
            role="assistant",
            agent_id=agent_id,
            content=content,
            created_at=when,
        )
        session.add(row)
        thread.next_seq += 1
        await session.flush()
        return message_data(row)


async def write(
    fixture: Fixture,
    thread_id: str,
    role: str,
    agent_id: str | None,
    content: str,
    when: datetime,
    **extra: Any,
) -> MessageRow:
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        row = MessageRow(
            thread_id=thread_id,
            seq=thread.next_seq,
            role=role,
            agent_id=agent_id,
            content=content,
            created_at=when,
            **extra,
        )
        session.add(row)
        thread.next_seq += 1
        await session.flush()
        session.expunge(row)
        return row


async def run(
    fixture: Fixture,
    thread_id: str,
    agent_id: str,
    seq: int,
    status: str,
    when: datetime,
    code: str | None = None,
):
    async with fixture.runtime.db.sessions() as session, session.begin():
        session.add(
            RunRow(
                thread_id=thread_id,
                agent_id=agent_id,
                trigger="user",
                status=status,
                input_seq=seq,
                error_code=code,
                created_at=when,
                updated_at=when,
            )
        )


CONVERSATION_MD = (
    "## ملخص الفائدة\n"
    "- ثبّت البنك المركزي السعر هذا الأسبوع\n"
    "- تميل التوقعات إلى خفض في الربع القادم\n\n"
    '```json\n{"rate": 5.25, "next": "cut"}\n```'
)


async def conversation(fixture: Fixture, seed: dict[str, Any]) -> dict[str, Any]:
    """The conversation states: Markdown with a code block, a reply quote, reactions of the
    owner, a failed reply (rate family) and a missed call, in the research agent's chat."""
    thread = seed["threads"]["research"]
    agent = seed["agents"]["research"]
    ask = await write(fixture, thread, "user", None, "لخّص لي آخر تقرير عن الفائدة", at(9, 10))
    await run(fixture, thread, agent, ask.seq, "completed", at(9, 10))
    answer = await write(fixture, thread, "assistant", agent, CONVERSATION_MD, at(9, 11))
    async with fixture.runtime.db.sessions() as session, session.begin():
        session.add(
            MessageReactionRow(message_id=answer.id, thread_id=thread, reactor="owner", emoji="👍")
        )
    follow = await write(
        fixture, thread, "user", None, "اشرح لي الكود باختصار", at(9, 12), reply_to=answer.id
    )
    await run(fixture, thread, agent, follow.seq, "failed", at(9, 12), "model_rate_limited")
    await write(
        fixture,
        thread,
        "system",
        agent,
        "مكالمة صوتية فائتة",
        at(9, 20),
        rich_content={
            "version": 1,
            "parts": [
                {"type": "call", "direction": "incoming", "duration_seconds": 0, "missed": True}
            ],
        },
    )
    await fixture.request("POST", f"/threads/{thread}/read", {"seq": follow.seq + 1})
    return {"answer": answer.id}


async def rows(fixture: Fixture, path: str) -> list[dict[str, Any]]:
    response = await fixture.client.get("/api" + path)
    assert response.is_success, f"GET {path}: HTTP {response.status_code}"
    return response.json()


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [
        {"name": cookie.name, "value": cookie.value or ""} for cookie in fixture.client.cookies.jar
    ]


def candles() -> list[dict[str, str]]:
    """Five-minute XAUUSD bars along the reference's demo formula, ending 10:00 UTC today."""
    end = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
    close = [2355 - (145 - j * 2.2 + math.sin(j * 1.7) * 18) / 10 for j in range(-60, 30)]
    rows = []
    for index in range(1, len(close)):
        o, c = close[index - 1], close[index]
        rows.append(
            {
                "symbol": "XAUUSD",
                "timeframe": "5m",
                "time": (end - timedelta(minutes=5 * (len(close) - 1 - index))).isoformat(),
                "open": f"{o:.2f}",
                "high": f"{max(o, c) + 1.1:.2f}",
                "low": f"{min(o, c) - 1.1:.2f}",
                "close": f"{c:.2f}",
                "volume": "1",
            }
        )
    return rows


async def attach(fixture: Fixture, agents: list[dict[str, Any]]) -> dict[str, Any]:
    """A database this script seeded before: the same ids, a fresh sign-in."""
    names = {
        "Lonora": "lonora",
        "محلل الذهب": "gold",
        "مساعد الأبحاث": "research",
        "رفيق": "friend",
    }
    ids = {names[agent["name"]]: agent["id"] for agent in agents if agent["name"] in names}
    groups = await rows(fixture, "/groups")
    team = next(group for group in groups if group["payload"]["name"] == "فريق التداول")
    inbox = await rows(fixture, "/threads/inbox")
    threads = {key: e["thread_id"] for key, i in ids.items() for e in inbox if e["agent_id"] == i}
    threads["team"] = team["state"]["thread_id"]
    return {"cookies": cookies(fixture), "agents": ids, "group": team["id"], "threads": threads}


async def init(fixture: Fixture) -> dict[str, Any]:
    agents = await rows(fixture, "/agents")
    if any(agent["name"] == "محلل الذهب" for agent in agents):
        return await attach(fixture, agents)
    if len(agents) != 1:
        raise SystemExit("seed_reference expects a fresh database (one personal agent).")
    lonora = agents[0]
    await fixture.request("PATCH", f"/agents/{lonora['id']}", {"color": "#7c83fd"})
    account = await fixture.request(
        "POST",
        "/trading/connections",
        {"provider": "simulation", "account_id": "ui-reference-demo", "enabled": True},
    )
    await fixture.request(
        "POST",
        f"/trading/connections/{account['id']}/simulation",
        {
            "snapshot": {
                "balance": "10000",
                "currency": "USD",
                # Phase 4a: the chart sheet draws real candles (the reference's own curve).
                "candles": {"XAUUSD:5m": candles()},
                "quotes": {
                    "XAUUSD": {
                        "symbol": "XAUUSD",
                        "bid": "2339.90",
                        "ask": "2340.00",
                        "observed_at": datetime.now(UTC).isoformat(),
                        "source": "simulation/imported-fixture",
                    }
                },
                "instruments": [
                    {
                        "symbol": "XAUUSD",
                        "digits": 2,
                        "tick_size": "0.01",
                        "volume_min": "0.01",
                        "volume_max": "100",
                        "volume_step": "0.01",
                    }
                ],
            }
        },
    )
    gold = await fixture.request(
        "POST",
        "/agents/create",
        {
            "template": "trading",
            "name": "محلل الذهب",
            "responsibility": "تحليل السوق ومتابعة الذهب",
            "market": "XAUUSD",
        },
    )
    # The trades page's open position (the reference's demo trade), opened by the owner
    # through the executor; the trading controls are put back as they were.
    controls = await fixture.request("GET", "/trading/controls")
    await fixture.request("PUT", "/trading/controls", {"enabled": True, "emergency_stop": False})
    await fixture.request(
        "POST",
        "/trading/execute",
        {
            "account_id": account["id"],
            "operation_id": str(uuid4()),
            "action": "buy",
            "symbol": "XAUUSD",
            "volume": "0.01",
            "stop_loss": "2335",
            "take_profit": "2350",
        },
    )
    await fixture.request("PUT", "/trading/controls", controls)
    research = await fixture.request(
        "POST",
        "/agents/create",
        {
            "template": "research",
            "name": "مساعد الأبحاث",
            "responsibility": "جمع المعلومات وتلخيصها",
        },
    )
    friend = await fixture.request(
        "POST",
        "/agents/create",
        {"template": "general", "name": "رفيق", "responsibility": "تنظيم المهام اليومية"},
    )
    for agent, color in ((gold, "#8b5cf6"), (research, "#5d9cec"), (friend, "#55bca6")):
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"color": color})
    group = await fixture.request(
        "POST",
        "/groups/create",
        {
            "name": "فريق التداول",
            "member_ids": [lonora["id"], gold["id"], research["id"]],
            "participation": "mentions_or_lead",
            "purpose": "متابعة السوق وتنسيق العمل",
            "lead_agent_id": lonora["id"],
        },
    )
    threads = {
        "lonora": (await fixture.conversation(lonora))["id"],
        "gold": (await fixture.conversation(gold))["id"],
        "research": (await fixture.conversation(research))["id"],
        "friend": (await fixture.conversation(friend))["id"],
        "team": group["thread_id"],
    }
    await say(
        fixture,
        threads["gold"],
        gold["id"],
        "الذهب يقترب من مقاومة 2350. سأنبّهك عند أي اختراق، ويمكنك فتح الشارت من الاقتراحات أسفل المحادثة.",
        at(9, 41),
    )
    lonora_seed = await say(
        fixture,
        threads["lonora"],
        lonora["id"],
        "صباح الخير أحمد! موجز اليوم جاهز: لا مستجدات عاجلة، ومهمة متابعة الذهب مستمرة حتى 18:00.",
        at(9, 0),
    )
    team_first = await say(
        fixture,
        threads["team"],
        lonora["id"],
        "مرحبًا بالفريق. كل وكيل هنا يحتفظ بصلاحياته الخاصة.",
        at(8, 30),
    )
    await say(
        fixture,
        threads["team"],
        research["id"],
        "جمعت ثلاثة مصادر عن توقعات الفائدة هذا الأسبوع. أرسلها لكم كملخص؟",
        at(8, 32),
    )
    # The reference's unread map: gold 1, team 1 (Lonora's briefing was read).
    await fixture.request("POST", f"/threads/{threads['lonora']}/read", {"seq": lonora_seed["seq"]})
    await fixture.request("POST", f"/threads/{threads['team']}/read", {"seq": team_first["seq"]})
    return {
        "cookies": cookies(fixture),
        "agents": {
            "lonora": lonora["id"],
            "gold": gold["id"],
            "research": research["id"],
            "friend": friend["id"],
        },
        "group": group["id"],
        "threads": threads,
    }


async def main(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        if data["action"] == "init":
            return await init(fixture)
        if data["action"] == "conversation":
            return await conversation(fixture, await init(fixture))
        raise ValueError("Unknown seed action")
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(json.load(sys.stdin)))))
