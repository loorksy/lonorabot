"""Only the owner assigns an agent's model (VISION 12.3) on disposable PostgreSQL.

Exercises the owner's model API, ``model_request`` (applied at once only when the owner's
typed message this run answers names the model; otherwise refused with nothing changed and
no card), Lonora assigning another agent's model on the owner's words, a new agent
starting on Lonora's current model (3.1.2), ``subagent_spawn`` and ``consult_model`` on any
catalog model of a connected provider, and per-agent usage. A change touches only the
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
from lonora_db.personal_agent import ensure_personal_agent
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
# In a connected provider's catalog, and in no route, backup or list of the owner's.
HAIKU = ModelSelection(provider="anthropic", model="claude-haiku-test")
UNCONNECTED = ModelSelection(provider="deepseek", model="deepseek-chat")
# Records a change may touch; every other table must stay exactly as it was.
CHANGE_TABLES = {"ln_settings", "ln_events", "ln_effect_receipts"}
REFUSED = "model_assignment_requires_owner_message"


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
            catalogs = {"openai": [DEFAULT], "anthropic": [SONNET, OPUS, HAIKU]}
            for provider, models in catalogs.items():
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

        # 1. The owner's API: no mode, no allowed list; every catalog model to pick.
        gone = await fixture.client.get("/api/settings/models/allowed")
        assert gone.status_code in {404, 405}, gone.status_code
        agent = await fixture.agent("Model chooser")
        thread = await fixture.conversation(agent)
        path = f"/agents/{agent['id']}/model"
        summary = await fixture.request("GET", path + "/summary")
        assert "mode" not in summary["record"] and "allowed" not in summary
        assert summary["current"]["model"] == DEFAULT.model
        assert {item["model"] for item in summary["available"]} == {
            DEFAULT.model,
            SONNET.model,
            OPUS.model,
            HAIKU.model,
        }
        assert summary["usage"]["requests"] == 0
        refused_mode = await fixture.client.put(
            "/api" + path, json={"mode": "fixed", "primary": SONNET.model_dump()}
        )
        assert refused_mode.status_code == 422
        print("PASS the owner's model API has no mode and no allowed list")

        async def wake(to: dict[str, Any], conversation: dict[str, Any]) -> Any:
            # A run that answers no owner message: a routine wake.
            run = await fixture.request(
                "POST",
                "/runs",
                {
                    "agent_id": to["id"],
                    "thread_id": conversation["id"],
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

        async def record(agent_id: str | None = None) -> dict[str, Any]:
            return await fixture.request("GET", f"/agents/{agent_id or agent['id']}/model")

        async def no_cards() -> None:
            async with db.sessions() as session:
                assert not await session.scalar(select(func.count()).select_from(OwnerActionRow))

        async def owner_says(words: str, to: dict[str, Any], conversation: dict[str, Any]):
            """The owner's message in a conversation; a Run already working there takes
            it as steering, otherwise it starts a new owner-message Run."""
            sent = await fixture.request(
                "POST",
                f"/threads/{conversation['id']}/messages",
                {"content": words, "client_nonce": "model-" + uuid4().hex},
            )
            run = {"id": sent["run_ids"][0], "agent_id": to["id"], "thread_id": conversation["id"]}
            return await fixture.lease(run)

        async def finish(context: Any) -> None:
            """End every fixture Run still open in this conversation, so the owner's next
            message starts a new Run."""
            async with db.sessions() as session, session.begin():
                rows = await session.scalars(
                    select(RunRow)
                    .where(
                        RunRow.thread_id == context.thread_id,
                        RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
                    )
                    .with_for_update()
                )
                for row in rows:
                    row.status = "completed"

        # 2. (b) Without the owner's message (a routine run) nothing changes, no card.
        context = await wake(agent, thread)
        before = await counts()
        refused = await call(context, {"model": SONNET.model_dump()})
        assert refused["code"] == REFUSED and refused["changed"] is False, refused
        assert refused["recovery"].startswith("Nothing changed. Only the owner assigns")
        after = await counts()
        assert {name for name in before if before[name] != after[name]} == {"ln_effect_receipts"}
        assert (await record())["preference"]["primary"] is None
        await no_cards()
        await finish(context)
        print("PASS without the owner's message nothing changes and no card is raised")

        # 3. (a)(e) The owner's typed message names the model: it applies at once, no card,
        #    even for a model in no route, backup or list of his.
        owner_context = await owner_says("Use Claude Haiku from now on", agent, thread)
        async with db.sessions() as session:
            state_before = (await session.get(RunRow, owner_context.lease.run_id)).execution_state  # type: ignore[union-attr]
        before = await counts()
        call_id = "assign-" + uuid4().hex
        applied = await call(owner_context, {"model": HAIKU.model_dump()}, call_id)
        assert applied["changed"] is True and applied["ok"] is True, applied
        assert "owner_action" not in applied and "undo_card" not in applied
        after = await counts()
        assert {name for name in before if before[name] != after[name]} <= CHANGE_TABLES
        async with db.sessions() as session:
            state_after = (await session.get(RunRow, owner_context.lease.run_id)).execution_state  # type: ignore[union-attr]
        assert state_after == state_before  # No tool call is dropped or repeated.
        current = await record()
        assert current["preference"]["primary"] == HAIKU.model_dump()
        assert current["chosen_by"] == "owner" and current["chosen_by_agent_id"] == agent["id"]
        assert current["previous"] == {"primary": None, "fallbacks": []}
        assert "mode" not in current
        # A crash-replayed call answers as it did and adds nothing.
        assert await call(owner_context, {"model": HAIKU.model_dump()}, call_id) == applied
        async with db.sessions() as session:
            updates = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "agent.model.updated", EventRow.agent_id == agent["id"]
                    )
                )
            )
        assert [(event.payload["via"], event.payload["chosen_by"]) for event in updates] == [
            ("model_request", "owner")
        ]
        # The change records the owner's message it answered.
        assert updates[0].payload["source_message_id"]
        await no_cards()
        print("PASS the owner's message naming any catalog model applies it at once, no card")

        # 4. The router asks the new model on the next turn, with the whole history.
        calls: list[tuple[str, str, int]] = []
        services = fixture.runtime.services(fixture.owner)

        def scripted(provider: str, _secret: str) -> Any:
            return cast(Any, ScriptedAdapter(provider, calls))

        router = GlobalModelRouter(db, ProviderCredentials(db, services.secrets), scripted)
        history = [
            ModelMessage(role="system", content="explicit fixture"),
            ModelMessage(role="user", content="analyze gold"),
        ]
        _, used = await router.complete(
            Capability.CONVERSATION, history, [], owner_id=fixture.owner, agent_id=agent["id"]
        )
        assert used == HAIKU and calls[-1][1] == HAIKU.model
        print("PASS the next model turn uses the assigned model")

        # 5. (c) The owner's message names another model: this one does not apply.
        await finish(owner_context)
        named = await owner_says("Switch to sonnet please", agent, thread)
        other = await call(named, {"model": OPUS.model_dump()})
        assert other["code"] == REFUSED and other["changed"] is False, other
        assert (await record())["preference"]["primary"] == HAIKU.model_dump()
        switched = await call(named, {"model": SONNET.model_dump()})
        assert switched["changed"] is True, switched
        assert (await record())["previous"]["primary"] == HAIKU.model_dump()
        # Words the owner adds while the Run works count too (steering).
        steered = await owner_says("Actually use Opus", agent, thread)
        assert steered.lease.run_id == named.lease.run_id
        assert (await call(steered, {"model": OPUS.model_dump()}))["changed"] is True
        unknown = await call(steered, {"model": {"provider": "anthropic", "model": "claude-x"}})
        assert unknown["code"] == "model_not_in_catalog" and unknown["changed"] is False
        missing = await call(steered, {"model": UNCONNECTED.model_dump()})
        assert missing["code"] == "model_provider_not_connected"
        await finish(steered)
        unrelated = await owner_says("What is the gold outlook today?", agent, thread)
        assert (await call(unrelated, {"model": SONNET.model_dump()}))["code"] == REFUSED
        assert (await record())["preference"]["primary"] == OPUS.model_dump()
        await finish(unrelated)
        await no_cards()
        print("PASS only the model the owner's message names applies; others refuse")

        # 6. (d) A team agent never changes another agent's model, even on the owner's words.
        peer = await fixture.agent("Other agent")
        peer_thread = await fixture.conversation(peer)
        told_peer = await owner_says(
            "Put the model chooser on claude-sonnet-test", peer, peer_thread
        )
        try:
            await call(told_peer, {"model": SONNET.model_dump(), "agent_id": agent["id"]})
        except LonoraError as error:
            assert error.code == "model_request_agent_forbidden"
        else:
            raise AssertionError("A team agent must not change another agent's model")
        assert (await record())["preference"]["primary"] == OPUS.model_dump()
        await finish(told_peer)
        # Lonora does, only on the owner's words.
        async with db.sessions() as session, session.begin():
            lonora = {"id": (await ensure_personal_agent(session, fixture.owner)).id}
        lonora_thread = await fixture.conversation(lonora)
        vague = await owner_says("Make the model chooser faster", lonora, lonora_thread)
        routed = await call(vague, {"model": DEFAULT.model_dump(), "agent_id": agent["id"]})
        assert routed["code"] == REFUSED, routed
        await finish(vague)
        told = await owner_says("Put the model chooser on gpt-default-test", lonora, lonora_thread)
        routed = await call(told, {"model": DEFAULT.model_dump(), "agent_id": agent["id"]})
        assert routed["changed"] is True, routed
        moved = await record()
        assert moved["preference"]["primary"] == DEFAULT.model_dump()
        assert moved["chosen_by"] == "owner" and moved["chosen_by_agent_id"] == lonora["id"]
        await finish(told)
        await no_cards()
        print("PASS only Lonora changes another agent's model, on the owner's words")

        # 7. model_list: the facts, no mode and no allowed list; exact ids by name.
        context = await wake(agent, thread)
        facts = await registry.execute(
            ToolCall(id="list-" + uuid4().hex, name="model_list", arguments={"query": "Opus"}),
            context,
        )
        assert "mode" not in facts and "allowed" not in facts, facts
        assert facts["answering"]["model"] == DEFAULT.model and facts["chosen_by"] == "owner"
        assert facts["matches"][0] == {**OPUS.model_dump(), "name": "Claude-Opus"}
        guessed = await call(context, {"model": {"provider": "anthropic", "model": "claude-haiku"}})
        assert guessed["code"] == "model_not_in_catalog", guessed
        assert guessed["closest"][0] == {**HAIKU.model_dump(), "name": "Claude-Haiku"}
        print("PASS model_list shows the model answering now and exact ids by name")

        # 8. (f) A new agent created without a model starts on Lonora's current model.
        created = await fixture.request(
            "POST",
            "/agents/create",
            {"template": "research", "name": "Plain " + uuid4().hex[:6]},
        )
        assert (await record(created["id"]))["preference"]["primary"] is None
        await fixture.request(
            "PUT", f"/agents/{lonora['id']}/model", {"primary": OPUS.model_dump()}
        )
        inherited = await fixture.request(
            "POST",
            "/agents/create",
            {"template": "research", "name": "Inherits " + uuid4().hex[:6]},
        )
        snapshot = await record(inherited["id"])
        assert snapshot["preference"]["primary"] == OPUS.model_dump(), snapshot
        assert snapshot["chosen_by"] == "inherited"
        assert snapshot["chosen_by_agent_id"] == lonora["id"]
        route = await router.route(
            Capability.CONVERSATION, owner_id=fixture.owner, agent_id=inherited["id"]
        )
        assert route.choices[0] == OPUS
        # A snapshot: Lonora's later change leaves it as it was.
        await fixture.request(
            "PUT", f"/agents/{lonora['id']}/model", {"primary": SONNET.model_dump()}
        )
        assert (await record(inherited["id"]))["preference"]["primary"] == OPUS.model_dump()
        # A model the owner named at creation is the owner's.
        named_at_creation = await fixture.request(
            "POST",
            "/agents/create",
            {
                "template": "research",
                "name": "Named " + uuid4().hex[:6],
                "model": HAIKU.model_dump(),
            },
        )
        own = await record(named_at_creation["id"])
        assert own["preference"]["primary"] == HAIKU.model_dump() and own["chosen_by"] == "owner"
        await fixture.request("PUT", f"/agents/{lonora['id']}/model", {"primary": None})
        print("PASS a new agent starts on Lonora's current model, as a snapshot")

        # 9. A helper on any catalog model of a connected provider, first in its chain.
        refused = await registry.execute(
            ToolCall(
                id="spawn-" + uuid4().hex,
                name="subagent_spawn",
                arguments={"task": "explicit fixture", "model": UNCONNECTED.model_dump()},
            ),
            context,
        )
        assert refused["code"] == "subagent_model_not_available", refused
        spawned = await registry.execute(
            ToolCall(
                id="spawn-" + uuid4().hex,
                name="subagent_spawn",
                arguments={"task": "explicit fixture", "model": HAIKU.model_dump()},
            ),
            context,
        )
        async with db.sessions() as session:
            child = await session.get(RunRow, spawned["id"])
            assert child is not None
            chosen = run_model_choice(child.model_metadata.get("model"))
        assert chosen == HAIKU
        route = await router.route(
            Capability.CONVERSATION,
            owner_id=fixture.owner,
            agent_id=agent["id"],
            run_choice=chosen,
        )
        assert route.choices[0] == HAIKU and DEFAULT in route.choices
        print("PASS a helper starts on any available model, its agent's chain behind")

        # 10. consult_model asks any catalog model of a connected provider it names.
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
                arguments={"question": "Is this sound?", "model": HAIKU.model_dump()},
            ),
            recording,
        )
        assert opinion["model"] == HAIKU.model_dump() and consulted[-1] == [HAIKU], opinion
        outside = await registry.execute(
            ToolCall(
                id="consult-" + uuid4().hex,
                name="consult_model",
                arguments={"question": "Is this sound?", "model": UNCONNECTED.model_dump()},
            ),
            recording,
        )
        assert outside["code"] == "consult_model_not_configured", outside
        print("PASS consult_model uses any available model it names")

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
