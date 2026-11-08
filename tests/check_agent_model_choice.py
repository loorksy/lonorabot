"""Choosing a model from chat (W15-10) on disposable PostgreSQL.

Exercises the owner's model card API (Automatic / Fixed), the allowed list, the agent's
``model_request`` tool with its owner cards and Undo, ``subagent_spawn`` and
``consult_model`` on a chosen model, and per-agent usage. A switch changes only the
model choice: no other record changes and nothing is repeated. No real provider is
called; a scripted adapter answers.
"""

import asyncio
from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.usage import TokenUsage
from lonora_core.user_error import LonoraError
from lonora_db.schema import Base, EventRow, OwnerActionRow, RunRow
from lonora_db.transactions import SettingsRepository
from lonora_gateway.run_dispatch import run_model_choice
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.router import GlobalModelRouter
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

DEFAULT = ModelSelection(provider="openai", model="gpt-default-test")
SONNET = ModelSelection(provider="anthropic", model="claude-sonnet-test")
OPUS = ModelSelection(provider="anthropic", model="claude-opus-test")
UNCONNECTED = ModelSelection(provider="deepseek", model="deepseek-chat")
# Records a switch may touch; every other table must stay exactly as it was.
SWITCH_TABLES = {"ln_settings", "ln_events", "ln_owner_actions", "ln_effect_receipts"}


class ScriptedAdapter:
    def __init__(self, provider: str, calls: list[tuple[str, str, int]]):
        self.provider, self.calls = provider, calls

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        **_: Any,
    ) -> ModelReply:
        self.calls.append((self.provider, model, len(messages)))
        return ModelReply(text="explicit scripted reply from " + model)

    async def close(self) -> None:
        return None


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    registry = load_tools()
    try:
        # The owner's models: one default for text work, two connected providers.
        await fixture.request(
            "PUT", "/settings/models", {"mode": "unified", "unified": DEFAULT.model_dump()}
        )
        for provider in ("openai", "anthropic"):
            await fixture.request(
                "PUT", f"/providers/{provider}/credential", {"api_key": "explicit-test-key-1234"}
            )
        async with db.sessions() as session, session.begin():
            for provider, models in {"openai": [DEFAULT], "anthropic": [SONNET, OPUS]}.items():
                await SettingsRepository().put(
                    session,
                    "catalog:" + provider,
                    {
                        "models": [
                            {
                                "id": item.model,
                                "provider": provider,
                                "name": item.model.replace("-test", "").title(),
                                "source": "explicit-fixture",
                            }
                            for item in models
                        ]
                    },
                )

        # 1. The allowed list: the default route always, the owner's additions on top.
        allowed = await fixture.request("GET", "/settings/models/allowed")
        assert allowed["routed"] == [DEFAULT.model_dump()] and allowed["added"] == []
        saved = await fixture.request(
            "PUT", "/settings/models/allowed", {"added": [SONNET.model_dump()]}
        )
        assert saved["added"] == [SONNET.model_dump()]
        print("PASS the allowed list is the owner's routes plus the owner's additions")

        agent = await fixture.agent("Model chooser")
        thread = await fixture.conversation(agent)
        path = f"/agents/{agent['id']}/model"
        summary = await fixture.request("GET", path + "/summary")
        assert summary["record"]["mode"] == "automatic"
        assert summary["current"]["model"] == DEFAULT.model
        assert {item["model"] for item in summary["allowed"]} == {DEFAULT.model, SONNET.model}
        assert {item["model"] for item in summary["available"]} == {
            DEFAULT.model,
            SONNET.model,
            OPUS.model,
        }
        assert summary["usage"]["requests"] == 0

        async def wake() -> Any:
            # A run that answers no owner message: a routine wake.
            run = await fixture.request(
                "POST",
                "/runs",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "trigger": "routine",
                    "prompt": "Explicit scheduled fixture",
                },
            )
            return await fixture.lease(run)

        async def call(context: Any, arguments: dict[str, Any], call_id: str | None = None):
            return await registry.execute(
                ToolCall(
                    id=call_id or "model-" + uuid4().hex, name="model_request", arguments=arguments
                ),
                context,
            )

        async def counts() -> dict[str, int]:
            async with db.sessions() as session:
                return {
                    table.name: int(
                        await session.scalar(select(func.count()).select_from(table)) or 0
                    )
                    for table in Base.metadata.sorted_tables
                }

        async def record() -> dict[str, Any]:
            return await fixture.request("GET", path)

        async def cards() -> list[dict[str, Any]]:
            response = await fixture.client.get(
                "/api/owner-actions", params={"thread_id": thread["id"]}
            )
            assert response.is_success, response.text
            return cast(list[dict[str, Any]], response.json())

        async def decide(card_id: str, decision: str) -> dict[str, Any]:
            return await fixture.request(
                "POST", f"/owner-actions/{card_id}/decision", {"decision": decision}
            )

        # 2. Automatic: the agent's own switch to an allowed model applies at once,
        #    is logged, changes nothing else and offers Undo.
        context = await wake()
        async with db.sessions() as session:
            state_before = (await session.get(RunRow, context.lease.run_id)).execution_state  # type: ignore[union-attr]
        before = await counts()
        call_id = "switch-" + uuid4().hex
        switched = await call(context, {"model": SONNET.model_dump()}, call_id)
        assert switched["changed"] is True and switched["mode"] == "automatic", switched
        after = await counts()
        changed = {name for name in before if before[name] != after[name]}
        assert changed <= SWITCH_TABLES, changed
        async with db.sessions() as session:
            state_after = (await session.get(RunRow, context.lease.run_id)).execution_state  # type: ignore[union-attr]
        assert state_after == state_before  # No tool call is dropped or repeated.
        current = await record()
        assert current["preference"]["primary"] == SONNET.model_dump()
        assert current["chosen_by"] == "agent" and current["mode"] == "automatic"
        assert current["previous"]["preference"]["primary"] is None
        # A crash-replayed call answers as it did and adds nothing.
        replayed = await call(context, {"model": SONNET.model_dump()}, call_id)
        assert replayed == switched
        async with db.sessions() as session:
            updates = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "agent.model.updated", EventRow.agent_id == agent["id"]
                    )
                )
            )
        assert [(event.payload["via"], event.payload["chosen_by"]) for event in updates] == [
            ("model_request", "agent")
        ]
        undo = next(card for card in await cards() if card["kind"] == "agent_model_changed")
        assert undo["status"] == "pending" and undo["id"] == switched["undo_card"]
        facts = undo["facts"]["model"]
        assert facts["current"]["model"]["model"] == SONNET.model
        assert facts["previous"]["model"]["model"] is None
        assert facts["default_model"]["model"] == DEFAULT.model
        print("PASS an automatic agent switches itself within the list; nothing else changes")

        # 3. The router asks the new model on the next turn, with the whole history.
        calls: list[tuple[str, str, int]] = []
        services = fixture.runtime.services(fixture.owner)
        router = GlobalModelRouter(
            db,
            ProviderCredentials(db, services.secrets),
            lambda provider, _secret: cast(Any, ScriptedAdapter(provider, calls)),
        )
        history = [
            ModelMessage(role="system", content="explicit fixture"),
            ModelMessage(role="user", content="analyze gold"),
        ]
        _, used = await router.complete(
            Capability.CONVERSATION, history, [], owner_id=fixture.owner, agent_id=agent["id"]
        )
        assert used == SONNET and calls[-1][1] == SONNET.model
        print("PASS the next model turn uses the chosen model")

        # 4. Undo restores the previous choice; a second tap changes nothing.
        undone = await decide(undo["id"], "confirm")
        assert undone["status"] == "confirmed"
        restored = await record()
        assert restored["preference"]["primary"] is None and restored["chosen_by"] == "owner"
        again = await decide(undo["id"], "confirm")
        assert (
            again["status"] == "confirmed" and (await record())["revision"] == restored["revision"]
        )
        _, used = await router.complete(
            Capability.CONVERSATION, history, [], owner_id=fixture.owner, agent_id=agent["id"]
        )
        assert used == DEFAULT
        print("PASS Undo restores the previous model once")

        # 5. A model outside the list raises a card; nothing changes until the tap,
        #    and the tap adds it to the list.
        context = await wake()
        asked = await call(context, {"model": OPUS.model_dump()})
        assert asked["changed"] is False and asked["owner_must_tap"] is True, asked
        assert asked["why"] == "outside_allowed_list"
        assert (await record())["preference"]["primary"] is None
        repeat = await call(context, {"model": OPUS.model_dump()})
        assert (
            repeat["owner_action"]["id"] == asked["owner_action"]["id"] and repeat["already_shown"]
        )
        request_card = next(
            card for card in await cards() if card["id"] == asked["owner_action"]["id"]
        )
        assert request_card["kind"] == "agent_model" and request_card["requires_passkey"] is False
        assert request_card["facts"]["model"]["allow"] is True
        assert request_card["facts"]["model"]["requested"]["model"]["name"] == "Claude-Opus"
        confirmed = await decide(asked["owner_action"]["id"], "confirm")
        assert confirmed["status"] == "confirmed" and confirmed["result"]["allowed_added"] is True
        assert (await record())["preference"]["primary"] == OPUS.model_dump()
        listed = await fixture.request("GET", "/settings/models/allowed")
        assert OPUS.model_dump() in listed["added"]
        print("PASS a model outside the list is one owner tap, then remembered")

        # 6. An agent the owner fixed asks; another agent's model is Lonora's to route.
        await fixture.request("PUT", path, {"mode": "fixed", "primary": DEFAULT.model_dump()})
        context = await wake()
        held = await call(context, {"model": SONNET.model_dump()})
        assert held["owner_must_tap"] is True and held["why"] == "owner_fixed_model", held
        assert (await record())["preference"]["primary"] == DEFAULT.model_dump()
        # The owner's own change ends the agent's pending request.
        await fixture.request("PUT", path, {"mode": "automatic"})
        async with db.sessions() as session:
            ended = await session.get(OwnerActionRow, held["owner_action"]["id"])
            assert ended is not None and ended.status == "superseded"
            assert ended.status_reason == "owner_changed_model"
        other = await fixture.agent("Other agent")
        try:
            await call(context, {"model": SONNET.model_dump(), "agent_id": other["id"]})
        except LonoraError as error:
            assert error.code == "model_request_agent_forbidden"
        else:
            raise AssertionError("A peer must not change another agent's model")
        print("PASS a fixed model is the owner's; peers never change another agent's model")

        # 7. The owner asked in this turn: applies at once, as the owner's choice.
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {"content": "Use Opus and keep it", "client_nonce": "model-" + uuid4().hex},
        )
        owner_run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        owner_context = await fixture.lease(owner_run)
        pinned = await call(owner_context, {"model": OPUS.model_dump(), "fixed": True})
        assert pinned["changed"] is True and pinned["mode"] == "fixed", pinned
        fixed = await record()
        assert fixed["mode"] == "fixed" and fixed["chosen_by"] == "agent"
        async with db.sessions() as session:
            asked_event = await session.scalar(
                select(EventRow)
                .where(
                    EventRow.kind == "agent.model.updated",
                    EventRow.run_id == owner_context.lease.run_id,
                )
                .limit(1)
            )
        # The switch records the owner's message it answered.
        assert asked_event is not None and asked_event.payload["source_message_id"]
        unknown = await call(
            owner_context, {"model": {"provider": "anthropic", "model": "claude-invented"}}
        )
        assert unknown["code"] == "model_not_in_catalog" and unknown["changed"] is False
        missing = await call(owner_context, {"model": UNCONNECTED.model_dump()})
        assert missing["code"] == "model_provider_not_connected"
        print("PASS the owner's request applies at once; unknown or unconnected models refuse")

        # 8. A switch limit per run.
        await fixture.request("PUT", path, {"mode": "automatic"})
        context = await wake()
        for model in (SONNET, DEFAULT, SONNET):
            assert (await call(context, {"model": model.model_dump()}))["changed"] is True
        limited = await call(context, {"model": DEFAULT.model_dump()})
        assert limited["code"] == "model_switch_limit", limited
        print("PASS at most three switches per run")

        # 9. A helper on a chosen model: only allowed models, first in its chain.
        context = await wake()
        refused = await registry.execute(
            ToolCall(
                id="spawn-" + uuid4().hex,
                name="subagent_spawn",
                arguments={"task": "explicit fixture", "model": UNCONNECTED.model_dump()},
            ),
            context,
        )
        assert refused["code"] == "subagent_model_not_allowed", refused
        spawned = await registry.execute(
            ToolCall(
                id="spawn-" + uuid4().hex,
                name="subagent_spawn",
                arguments={"task": "explicit fixture", "model": OPUS.model_dump()},
            ),
            context,
        )
        async with db.sessions() as session:
            child = await session.get(RunRow, spawned["id"])
            assert child is not None
            chosen = run_model_choice(child.model_metadata.get("model"))
        assert chosen == OPUS
        route = await router.route(
            Capability.CONVERSATION,
            owner_id=fixture.owner,
            agent_id=agent["id"],
            run_choice=chosen,
        )
        assert route.choices[0] == OPUS and SONNET in route.choices
        print("PASS a helper starts on its chosen allowed model, its agent's chain behind")

        # 10. consult_model asks the model the agent names from the allowed list.
        consulted: list[list[ModelSelection]] = []

        class Recording:
            credentials = router.credentials

            async def route(self, *args: Any, **kwargs: Any) -> Any:
                return await router.route(*args, **kwargs)

            async def complete(self, *args: Any, **kwargs: Any) -> Any:
                consulted.append(list(kwargs["choices"]))
                return await router.complete(*args, **kwargs)

        recording = replace(context, router=cast(Any, Recording()))
        opinion = await registry.execute(
            ToolCall(
                id="consult-" + uuid4().hex,
                name="consult_model",
                arguments={"question": "Is this sound?", "model": OPUS.model_dump()},
            ),
            recording,
        )
        assert opinion["model"] == OPUS.model_dump() and consulted[-1] == [OPUS], opinion
        outside = await registry.execute(
            ToolCall(
                id="consult-" + uuid4().hex,
                name="consult_model",
                arguments={"question": "Is this sound?", "model": UNCONNECTED.model_dump()},
            ),
            recording,
        )
        assert outside["code"] == "consult_model_not_configured", outside
        print("PASS consult_model uses the chosen allowed model")

        # 11. Usage per agent, from the recorded requests (owner decision D4: no cap).
        await save_usage(
            db,
            fixture.owner,
            agent["id"],
            thread["id"],
            UsageRecord(
                context.lease.run_id,
                SONNET.provider,
                SONNET.model,
                TokenUsage(input_tokens=1200, output_tokens=300),
            ),
        )
        usage = await fixture.request("GET", "/usage/agents?days=30")
        mine = next(item for item in usage["agents"] if item["agent_id"] == agent["id"])
        assert mine["input_tokens"] >= 1200 and mine["requests"] >= 1
        assert any(model["model"] == SONNET.model for model in mine["models"])
        summary = await fixture.request("GET", path + "/summary")
        assert summary["usage"]["input_tokens"] == mine["input_tokens"]
        print("PASS usage is shown per agent")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
