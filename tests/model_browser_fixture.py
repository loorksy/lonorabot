"""Explicit model-choice fixture for the Web and Mobile model card specs (W15-10).

Reads one JSON action on stdin. ``init`` gives the browser the owner session, sets one
default model and two connected providers with explicit catalogs, creates an agent with
its conversation, and has the agent ask for a model outside the allowed list from a
routine run, so the conversation shows an ``agent_model`` card. ``cleanup`` restores the
global model settings and removes the fixture keys, so later specs see what they saw
before. No real provider is called and no key is real.
"""

import asyncio
import json
import sys
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_db.model_credentials import credential_id
from lonora_db.schema import SecretRow
from lonora_db.transactions import SettingsRepository
from lonora_tools.loader import load_tools
from sqlalchemy import delete

SETTINGS = (
    "model_routing",
    "model_allowed",
    *("catalog:" + name for name in ("openai", "anthropic")),
)
CATALOGS = {
    "openai": [("gpt-default-ui", "GPT Default UI")],
    "anthropic": [("claude-sonnet-ui", "Claude Sonnet UI"), ("claude-opus-ui", "Claude Opus UI")],
}


async def action(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        if data["action"] == "cleanup":
            async with fixture.runtime.db.sessions() as session, session.begin():
                for key, value in data["restore"]["settings"].items():
                    await SettingsRepository().put(session, key, value)
                for provider in data["restore"]["added_keys"]:
                    await session.execute(
                        delete(SecretRow).where(
                            SecretRow.scope == "provider", SecretRow.name == provider
                        )
                    )
            # Its agent goes too, so it never counts against the owner's agent cap.
            if data["restore"].get("agent"):
                await fixture.client.delete("/api/agents/" + data["restore"]["agent"])
            return {"cleaned": True}
        if data["action"] != "init":
            raise ValueError("Unknown model browser fixture action")
        async with fixture.runtime.db.sessions() as session:
            restore = {
                "settings": {key: await SettingsRepository().get(session, key) for key in SETTINGS},
                "added_keys": [
                    provider
                    for provider in CATALOGS
                    if await credential_id(session, provider) is None
                ],
            }
        cookies = [
            {"name": cookie.name, "value": cookie.value} for cookie in fixture.client.cookies.jar
        ]
        await fixture.request(
            "PUT",
            "/settings/models",
            {"mode": "unified", "unified": {"provider": "openai", "model": "gpt-default-ui"}},
        )
        for provider in CATALOGS:
            await fixture.request(
                "PUT", f"/providers/{provider}/credential", {"api_key": "explicit-ui-key-1234"}
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            for provider, models in CATALOGS.items():
                await SettingsRepository().put(
                    session,
                    "catalog:" + provider,
                    {
                        "models": [
                            {"id": model, "provider": provider, "name": name, "source": "fixture"}
                            for model, name in models
                        ]
                    },
                )
        agent = await fixture.agent("Model card " + data.get("locale", "en"))
        restore["agent"] = agent["id"]
        thread = await fixture.conversation(agent)
        run = await fixture.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "trigger": "routine",
                "prompt": "Explicit routine fixture",
            },
        )
        context = await fixture.lease(run)
        asked = await load_tools().execute(
            ToolCall(
                id="model-ui-" + uuid4().hex,
                name="model_request",
                arguments={"model": {"provider": "anthropic", "model": "claude-opus-ui"}},
            ),
            context,
        )
        return {
            "cookies": cookies,
            "agent": agent,
            "thread": thread,
            "card": asked["owner_action"]["id"],
            "restore": restore,
        }
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
