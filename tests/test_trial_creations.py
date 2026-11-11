"""Nothing is created to try it.

An Agent that wants to see whether a tool works must not leave a switched-off watch or
routine behind as its test. Both create tools refuse ``enabled: false``; the owner's own
routes, goals and the evaluator still store disabled rows.
"""

import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_core.user_error import ToolRefusal
from lonora_db.schema import MarketWatchRow, RoutineRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_a_watch_or_a_routine_is_not_created_switched_off():
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The creation cases use the real migrated PostgreSQL schema.")
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Careful")
        thread = await fixture.conversation(agent)
        sent = await fixture.client.post(
            f"/api/threads/{thread['id']}/messages",
            json={"client_nonce": "trial-" + uuid4().hex, "content": "هل تستطيع المراقبة؟"},
        )
        context = await fixture.lease({**sent.json()["runs"][0], "thread_id": thread["id"]})
        tools = load_tools().tools

        async def count(row: Any) -> int:
            async with fixture.runtime.db.sessions() as session:
                return await session.scalar(
                    select(func.count()).select_from(row).where(row.agent_id == agent["id"])
                )

        watch = {"symbol": "XAUUSD", "condition": "above", "level": "2500", "prompt": "test"}
        for name, args, stop in (
            ("watch_create", {**watch, "enabled": False}, "watch_pause"),
            (
                "routine_create",
                {"prompt": "test", "interval_seconds": 3600, "enabled": False},
                "routine_toggle",
            ),
        ):
            with pytest.raises(ToolRefusal, match="create_disabled_refused") as refused:
                await tools[name].handler(context, args)
            assert refused.value.details["class"] == "input"
            assert refused.value.details["next_actions"] == [{"tool": stop}]
        assert await count(MarketWatchRow) == 0 and await count(RoutineRow) == 0
        # Created to run, it is created.
        made = await tools["routine_create"].handler(
            context, {"prompt": "Check gold.", "interval_seconds": 3600}
        )
        assert made["enabled"] is True and await count(RoutineRow) == 1
    finally:
        await fixture.close()
