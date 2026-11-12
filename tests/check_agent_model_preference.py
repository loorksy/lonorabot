"""Owner API for one Agent's model preference: revisioned, scoped, no authority."""

import asyncio
from typing import Any, cast

from check_streaming import Fixture
from lonora_contracts.model_routing import Capability
from lonora_db.schema import EventRow
from lonora_providers.router import GlobalModelRouter
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Model preference fixture")
        path = f"/agents/{agent['id']}/model"
        empty = await fixture.request("GET", path)
        assert empty["revision"] == 0 and empty["preference"]["primary"] is None
        saved = await fixture.request(
            "PUT",
            path,
            {
                "primary": {"provider": "anthropic", "model": "claude-sonnet-4-5"},
                "fallbacks": [{"provider": "openai", "model": "gpt-4.1"}],
                "expected_revision": 0,
            },
        )
        assert saved["revision"] == 1 and saved["agent_id"] == agent["id"]
        # The owner's choice; no mode is stored or accepted.
        assert saved["chosen_by"] == "owner" and "mode" not in saved
        moded = await fixture.client.put(
            "/api" + path, json={"mode": "automatic", "expected_revision": 1}
        )
        assert moded.status_code == 422
        stale = await fixture.client.put(
            "/api" + path,
            json={"primary": {"provider": "openai", "model": "gpt-4o"}, "expected_revision": 0},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
        duplicate = await fixture.client.put(
            "/api" + path,
            json={
                "primary": {"provider": "openai", "model": "gpt-4o"},
                "fallbacks": [{"provider": "openai", "model": "gpt-4o"}],
            },
        )
        assert duplicate.status_code == 422
        missing = await fixture.client.get("/api/agents/not-an-agent/model")
        assert missing.status_code == 404
        router = GlobalModelRouter(fixture.runtime.db, cast(Any, None))
        route = await router.route(
            Capability.CONVERSATION, owner_id=fixture.owner, agent_id=agent["id"]
        )
        # The Agent's own model leads; its fallback follows any global route.
        identities = [(item.provider, item.model) for item in route.choices]
        assert identities[0] == ("anthropic", "claude-sonnet-4-5")
        assert ("openai", "gpt-4.1") in identities[1:]
        async with fixture.runtime.db.sessions() as session:
            updates = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "agent.model.updated", EventRow.agent_id == agent["id"]
                    )
                )
            )
        assert [event.payload["revision"] for event in updates] == [1]
        print(
            "PASS agent model preference: revisioned owner API, duplicate and scope refusal, router order"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
