"""The authenticated durable runtime, then persistent context, steering and concurrency.

Explicit scripted model fixtures through the real API, gateway dispatch and agent loop on a
fresh migrated PostgreSQL database: owner sign-in and CSRF, encrypted credentials, turn
deduplication, durable memory, replies and events; context governance, history compaction,
nonce replay, admission without deadlocks, lease fencing, steering between a provider reply
and tool execution, steering attachments and an early answer to a waiting question.
"""

import asyncio
import base64
import json
import os
import re
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import lonora_agent.tool_loop as loop_module
from lonora_adapter_kit.context import token_estimate
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_adapters.models.fake import ScriptedModelAdapter
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_agent.context.compaction import compact_history
from lonora_agent.context.governance import (
    MAXIMUM_CONTEXT_CHARS,
    context_blocks,
    govern_context,
    message_size,
)
from lonora_agent.model_runtime import model_turn
from lonora_agent.runtime import AgentRuntime
from lonora_agent.skills.registry import built_in_skills
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_contracts.domain import AgentCreate, Contract, MessageCreate, utcnow
from lonora_contracts.model_routing import Capability
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.usage import TokenUsage
from lonora_core.user_error import LonoraError
from lonora_db.agents import agent_data, create_agent
from lonora_db.cancellation import cancel_run
from lonora_db.messages import send_message
from lonora_db.runs import complete_run, create_run, require_lease
from lonora_db.schema import (
    ArtifactRow,
    EffectReceiptRow,
    MessageRow,
    RunRow,
    SecretRow,
    ThreadRow,
    UsageRow,
)
from lonora_db.transactions import owned_thread
from lonora_gateway.run_dispatch import dispatch_one
from lonora_gateway.service import Gateway
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.engine import make_url

PASSED: list[str] = []


def check(name: str, condition: object) -> None:
    assert condition, name
    PASSED.append(name)
    print("PASS", name, flush=True)


def scripted(fixture: ScriptedModelAdapter) -> Callable[..., ScriptedModelAdapter]:
    """A provider factory that answers every route with the one scripted fixture."""

    def factory(provider: str, key: str) -> ScriptedModelAdapter:
        return fixture

    return factory


async def verify_runtime() -> None:
    settings = get_settings()
    app = create_app(settings)
    rt = app.state.runtime
    gateway = Gateway(rt.db, settings.encryption_key.get_secret_value(), settings.artifact_root)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as client:

            async def request(
                method: str, path: str, body: dict[str, Any] | None = None, expected: int = 200
            ) -> Any:
                response = await client.request(method, "/api" + path, json=body)
                assert response.status_code == expected, (path, response.status_code, response.text)
                return response.json()

            await request("GET", "/agents", expected=401)
            await request(
                "POST",
                "/onboarding",
                {
                    "email": "ci@example.com",
                    "password": "ci-only-owner-password",
                    "bootstrap_token": settings.bootstrap_token.get_secret_value(),
                },
                201,
            )
            login = await request(
                "POST",
                "/auth/login",
                {"email": "ci@example.com", "password": "ci-only-owner-password"},
            )
            await request("POST", "/agents", {"name": "Denied"}, 403)
            client.headers["X-CSRF-Token"] = login["csrf"]
            await request("POST", "/agents", {"name": "Unbound new bot"}, 422)
            async with rt.db.sessions() as session, session.begin():
                agent = agent_data(
                    await create_agent(
                        session, login["owner"]["id"], AgentCreate(name="CI legacy agent")
                    )
                )
            thread = await request("POST", "/threads", {"agent_id": agent["id"]}, 201)
            await request(
                "PUT", "/providers/openai/credential", {"api_key": "explicit-ci-fixture-key"}
            )
            await request(
                "PUT",
                "/settings/models",
                {
                    "mode": "unified",
                    "unified": {"provider": "openai", "model": "explicit-ci-fixture"},
                    "routes": {},
                },
            )
            services = rt.services(login["owner"]["id"])
            fixture = ScriptedModelAdapter(
                [
                    ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="remember",
                                name="memory_write",
                                arguments={"content": "Durable CI fact", "version": 1},
                            )
                        ]
                    ),
                    ModelReply(text="CI reply"),
                ]
            )
            services.router.factory = scripted(fixture)
            gateway.services[login["owner"]["id"]] = services
            body = {"content": "Remember this fact", "client_nonce": "ci-dedup-nonce"}
            first = await request("POST", f"/threads/{thread['id']}/messages", body, 202)
            repeated = await request("POST", f"/threads/{thread['id']}/messages", body, 202)
            assert first["message"]["id"] == repeated["message"]["id"]
            assert first["run_ids"] == repeated["run_ids"]
            assert await dispatch_one(
                rt.db,
                "ci-gateway",
                gateway.runtime,
                gateway.services,
                settings.encryption_key.get_secret_value(),
                settings.artifact_root,
                120,
                4,
            )
            run = await request("GET", "/runs/" + first["run_ids"][0])
            assert run["status"] == "completed"
            memory = await request("GET", f"/agents/{agent['id']}/memory")
            assert memory["content"].strip() == "Durable CI fact" and memory["version"] == 2
            messages = await request("GET", f"/threads/{thread['id']}/messages")
            assert len(messages) == 2 and messages[-1]["content"] == "CI reply"
            events = await request("GET", "/events")
            assert any(row["kind"] == "tool.completed" for row in events)
            assert all("_ln_public_cursor" not in row["payload"] for row in events)
            async with rt.db.sessions() as session:
                credentials = list((await session.scalars(select(SecretRow))).all())
                assert credentials and all(
                    "explicit-ci-fixture-key" not in str(row.ciphertext) for row in credentials
                )
            await request("POST", "/auth/logout")
            await request("GET", "/agents", expected=401)
            print(
                "PASS owner/CSRF, encrypted credentials, turn deduplication, shared runtime, durable memory/reply/events and logout"
            )
    finally:
        for services in gateway.services.values():
            await services.brokers.close()
        await rt.db.close()


async def verify_persistence() -> None:
    settings = get_settings().model_copy(
        update={
            "cookie_secure": False,
            "artifact_root": Path("/tmp/lonora-ci-persistence-artifacts"),
        }
    )
    app = create_app(settings)
    rt = app.state.runtime
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as client:

        async def req(
            method: str, path: str, body: dict[str, Any] | None = None, expected: int = 200
        ) -> Any:
            response = await client.request(method, "/api" + path, json=body)
            assert response.status_code == expected, (
                path,
                response.status_code,
                response.text[:200],
            )
            return response.json()

        login = await req(
            "POST", "/auth/login", {"email": "ci@example.com", "password": "ci-only-owner-password"}
        )
        client.headers["X-CSRF-Token"] = login["csrf"]
        owner = login["owner"]["id"]
        await req(
            "PUT", "/providers/openai/credential", {"api_key": "explicit-persistence-fixture-key"}
        )
        await req(
            "PUT",
            "/settings/models",
            {
                "mode": "unified",
                "unified": {"provider": "openai", "model": "explicit-fixture"},
                "routes": {},
            },
        )
        services = rt.services(owner)

        async def new_context(history_contents: list[str] | None = None) -> ToolContext:
            async with rt.db.sessions() as session, session.begin():
                agent = agent_data(
                    await create_agent(
                        session,
                        owner,
                        AgentCreate(name="Legacy regression actor " + str(uuid.uuid4())[:6]),
                    )
                )
            thread = await req("POST", "/threads", {"agent_id": agent["id"]}, 201)
            async with rt.db.sessions() as session, session.begin():
                row = await session.get(ThreadRow, thread["id"])
                for index, content in enumerate(history_contents or [], 1):
                    session.add(
                        MessageRow(thread_id=row.id, seq=index, role="user", content=content)
                    )
                row.next_seq = len(history_contents or []) + 1
                await session.flush()
                run = await create_run(
                    session, owner, RunRequest(thread_id=row.id, agent_id=agent["id"])
                )
                run.status = "leased"
                run.lease_owner = "persistence-worker"
                run.lease_fence = 1
                run.lease_expires_at = utcnow() + timedelta(seconds=120)
                lease = Lease(run_id=run.id, owner="persistence-worker", fence=run.lease_fence)
            return services.tool_context(agent["id"], thread["id"], lease, settings.artifact_root)

        async def finish(context: ToolContext) -> None:
            async with rt.db.sessions() as session, session.begin():
                await cancel_run(session, owner, context.lease.run_id)

        calls = [
            ToolCall(id="one", name="fixture_read", arguments={}),
            ToolCall(id="two", name="fixture_read", arguments={}),
        ]
        source = [
            ModelMessage(role="system", content="Keep identity"),
            ModelMessage(role="user", content="Keep this latest user instruction"),
            ModelMessage(role="assistant", content="", tool_calls=calls),
            ModelMessage(
                role="tool",
                content=json.dumps({"ok": True, "data": "x" * 70000}),
                tool_call_id="one",
            ),
            ModelMessage(
                role="tool",
                content=json.dumps({"ok": True, "data": "y" * 70000}),
                tool_call_id="two",
            ),
        ]
        bounded = govern_context(source, 2000)
        check(
            "context keeps the user instruction and both tool-result IDs under the budget",
            sum(message_size(m) for m in bounded) <= 2000
            and [m.tool_call_id for m in bounded if m.role == "tool"] == ["one", "two"]
            and any("latest user instruction" in m.content for m in bounded),
        )
        check(
            "context governance leaves the durable result objects unchanged",
            len(source[-1].content) > 70000
            and all(
                json.loads(m.content).get("result_omitted") for m in bounded if m.role == "tool"
            ),
        )
        financial = source[-1].model_copy(
            update={
                "content": json.dumps(
                    {
                        "ok": True,
                        "status": "confirmed",
                        "operation_id": "financial-fixture",
                        "broker_reference": "broker-fixture",
                        "details": "x" * 80000,
                    }
                )
            }
        )
        financial_view = govern_context([*source[:-1], financial], 2000)
        financial_result = json.loads(financial_view[-1].content)
        check(
            "omitting a large result preserves successful financial status and operation identity",
            financial_result["ok"]
            and financial_result["status"] == "confirmed"
            and financial_result["operation_id"] == "financial-fixture",
        )
        old = [
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="old", name="fixture_read", arguments={})],
            ),
            ModelMessage(role="tool", content="x" * 900, tool_call_id="old"),
        ]
        fresh = [
            ModelMessage(role="user", content="new"),
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="new", name="fixture_read", arguments={})],
            ),
            ModelMessage(role="tool", content="{}", tool_call_id="new"),
        ]
        trimmed = govern_context([ModelMessage(role="system", content="s"), *old, *fresh], 400)
        context_blocks([m for m in trimmed if m.role != "system"])
        check(
            "history trimming cannot leave orphaned tool results",
            all(m.tool_call_id != "old" for m in trimmed),
        )
        try:
            govern_context(
                [
                    ModelMessage(role="user", content="q"),
                    ModelMessage(role="tool", content="{}", tool_call_id="orphan"),
                ]
            )
        except LonoraError as error:
            check(
                "malformed tool exchanges stop before reaching a provider",
                error.code == "invalid_tool_exchange",
            )
        else:
            raise AssertionError("Orphan result accepted")

        for count, width, label in [(124, 4000, "large-history"), (12, 30000, "large-messages")]:
            context = await new_context(
                [f"fact-{i:04d} " + ("x" * width) + f" tail-{i:04d}" for i in range(1, count + 1)]
            )
            fixture = ScriptedModelAdapter(
                [
                    ModelReply(
                        text="Complete durable summary",
                        usage=TokenUsage(input_tokens=13, output_tokens=3),
                    )
                    for _ in range(30)
                ]
            )
            services.router.factory = scripted(fixture)
            await compact_history(context)
            async with rt.db.sessions() as session:
                row = await session.get(ThreadRow, context.thread_id)
                usage = list(
                    (
                        await session.scalars(
                            select(UsageRow).where(UsageRow.thread_id == context.thread_id)
                        )
                    ).all()
                )
                through = row.summary_seq
            seen: list[int] = []
            for request in fixture.requests:
                text = request[-1].content
                assert sum(message_size(m) for m in request) <= MAXIMUM_CONTEXT_CHARS
                for match in re.finditer(
                    r"<message seq='(\d+)'[^>]*>\n(.*?)\n</message>", text, re.S
                ):
                    index = int(match.group(1))
                    seen.append(index)
                    assert f"fact-{index:04d}" in match.group(
                        2
                    ) and f"tail-{index:04d}" in match.group(2)
            check(
                label + ": only fully supplied messages advance the summary cursor",
                seen == list(range(1, through + 1))
                and 0 < through < count
                and len(fixture.requests) > 1,
            )
            check(
                label + ": background compaction records actual provider token usage",
                len(usage) == len(fixture.requests)
                and sum(u.payload["input_tokens"] for u in usage) == 13 * len(fixture.requests),
            )
            await finish(context)

        context = await new_context(["short fact " + str(i) for i in range(121)])
        fixture = ScriptedModelAdapter([ModelReply(text="   ")])
        services.router.factory = scripted(fixture)
        try:
            await compact_history(context)
        except LonoraError as error:
            async with rt.db.sessions() as session:
                row = await session.get(ThreadRow, context.thread_id)
                seq = row.summary_seq
            check(
                "an empty provider summary never hides conversation history",
                error.code == "history_summary_empty" and seq == 0,
            )
        else:
            raise AssertionError("Empty summary accepted")
        await finish(context)

        context = await new_context()
        fixture = ScriptedModelAdapter([ModelReply(text="bounded response")])
        services.router.factory = scripted(fixture)
        tools = load_tools().definitions()
        await model_turn(context, source, tools, Capability.CONVERSATION)
        # Budgets follow the resolved model's window (docs/context-engine.md):
        # the request plus every schema fits the admitted token budget, and
        # characters are only the transport safety net sized from it (never
        # below MAXIMUM_CONTEXT_CHARS). The whole catalog is a worst case: a
        # Run sends only its native working set.
        limits = await services.router.context_limits(
            Capability.CONVERSATION, owner_id=owner, agent_id=context.agent_id
        )
        request = fixture.requests[-1]
        sent = sum(message_size(m) for m in request)
        size = sent + sum(len(t.model_dump_json()) for t in tools)
        tokens = sum(token_estimate(m, count=limits.count) for m in request) + sum(
            limits.count(t.model_dump_json()) + 64 for t in tools
        )
        check(
            "every model turn reserves room for tool schemas and governs new results",
            size <= limits.transport_chars
            and tokens <= limits.input_tokens
            and sent < sum(message_size(m) for m in source),
        )
        await finish(context)

        async with rt.db.sessions() as session, session.begin():
            agent = agent_data(
                await create_agent(session, owner, AgentCreate(name="Legacy replay actor"))
            )
        thread = await req("POST", "/threads", {"agent_id": agent["id"]}, 201)
        first_body = {"content": "first turn", "client_nonce": "original-message"}
        first = await req("POST", f"/threads/{thread['id']}/messages", first_body, 202)
        async with rt.db.sessions() as session, session.begin():
            run = await session.get(RunRow, first["run_ids"][0])
            run.status = "completed"
            run.result = "first answer"
        later = await req(
            "POST", f"/threads/{thread['id']}/messages", {"content": "later turn"}, 202
        )
        replay = await req("POST", f"/threads/{thread['id']}/messages", first_body, 202)
        check(
            "replaying an old nonce returns its original run without attaching later turns",
            replay["run_ids"] == first["run_ids"] and later["run_ids"] != replay["run_ids"],
        )
        async with rt.db.sessions() as session, session.begin():
            receipt = await session.get(EffectReceiptRow, "message:" + first["message"]["id"])
            await session.delete(receipt)
        legacy = await req("POST", f"/threads/{thread['id']}/messages", first_body, 202)
        check(
            "legacy nonce recovery excludes unrelated later runs",
            legacy["run_ids"] == first["run_ids"],
        )

        for operation in ["complete", "cancel"]:
            context = await new_context(["initial request"])
            async with rt.db.sessions() as writer:
                await writer.begin()
                await owned_thread(writer, owner, context.thread_id, lock=True)

                async def concurrent(
                    operation: str = operation, context: ToolContext = context
                ) -> Any:
                    async with rt.db.sessions() as session, session.begin():
                        if operation == "complete":
                            return await complete_run(session, context.lease, "stale answer", {})
                        return (await cancel_run(session, owner, context.lease.run_id)).status

                task = asyncio.create_task(concurrent())
                await asyncio.sleep(0.1)
                await send_message(
                    writer, owner, context.thread_id, MessageCreate(content="fresh instruction")
                )
                await asyncio.wait_for(writer.commit(), 4)
                result = await asyncio.wait_for(task, 4)
            check(
                operation + ": concurrent message admission does not deadlock",
                result == (False if operation == "complete" else "cancelled"),
            )
            if operation == "complete":
                await finish(context)

        parent = await new_context(["parent request"])
        child = await new_context()
        async with rt.db.sessions() as session, session.begin():
            row = await session.get(RunRow, child.lease.run_id)
            row.parent_run_id = parent.lease.run_id
            row.status = "completed"
            row.result = "child outcome"
        async with rt.db.sessions() as writer:
            await writer.begin()
            await owned_thread(writer, owner, parent.thread_id, lock=True)
            task = asyncio.create_task(return_outcome(rt.db, child.lease.run_id))
            await asyncio.sleep(0.1)
            await send_message(
                writer, owner, parent.thread_id, MessageCreate(content="new parent instruction")
            )
            await asyncio.wait_for(writer.commit(), 4)
            await asyncio.wait_for(task, 4)
        async with rt.db.sessions() as session:
            messages = list(
                (
                    await session.scalars(
                        select(MessageRow).where(MessageRow.thread_id == parent.thread_id)
                    )
                ).all()
            )
        check(
            "a child outcome and fresh parent message cannot deadlock",
            any("child outcome" in m.content for m in messages),
        )
        await finish(parent)

        context = await new_context()
        async with rt.db.sessions() as stale:
            await stale.get(RunRow, context.lease.run_id)
            async with rt.db.sessions() as writer, writer.begin():
                row = await writer.get(RunRow, context.lease.run_id, with_for_update=True)
                row.lease_fence += 1
            try:
                await require_lease(stale, context.lease, lock=True)
            except LonoraError as error:
                check(
                    "fencing refreshes an already-loaded ORM run before validation",
                    error.code == "stale_lease",
                )
            else:
                raise AssertionError("Stale ORM lease accepted")
        await finish(context)

        class EmptyArguments(Contract):
            pass

        # Built-in Skills name the tools they need; a fixture registry without
        # those names fails context build with skill_tool_unknown before any
        # provider call. Never-executed name stubs keep the fixtures minimal.
        async def skill_tool_stub(
            context: ToolContext, arguments: dict[str, Any]
        ) -> dict[str, Any]:
            raise AssertionError("skill tool name stub executed")

        skill_tool_stubs = [
            Tool(name, "Skill tool name stub", EmptyArguments, skill_tool_stub, True)
            for name in sorted(
                {
                    tool
                    for skill in built_in_skills().values()
                    for tool in skill.manifest.required_tools
                }
            )
        ]

        executions: list[str] = []

        async def read(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
            executions.append(context.call_id)
            return {"symbol": "XAUUSDm", "data": "x" * 90000}

        registry = ToolRegistry(
            [Tool("fixture_read", "Explicit read fixture", EmptyArguments, read, True)]
            + skill_tool_stubs
        )
        context = await new_context(["original tool request"])
        fixture = ScriptedModelAdapter(
            [ModelReply(tool_calls=calls), ModelReply(text="followed the new instruction")]
        )
        services.router.factory = scripted(fixture)
        entered = asyncio.Event()
        release = asyncio.Event()
        original_persist = loop_module.persist
        held = False

        async def persist(*args: Any, **kwargs: Any) -> None:
            nonlocal held
            await original_persist(*args, **kwargs)
            if args[3] and not held:
                held = True
                entered.set()
                await release.wait()

        loop_module.persist = persist
        try:
            task = asyncio.create_task(AgentRuntime(registry, 120, 24).execute(context))
            await asyncio.wait_for(entered.wait(), 5)
            await req(
                "POST",
                f"/threads/{context.thread_id}/messages",
                {"content": "new instruction between provider reply and tool execution"},
                202,
            )
            release.set()
            await asyncio.wait_for(task, 10)
        finally:
            loop_module.persist = original_persist
            release.set()
        request = fixture.requests[-1]
        context_blocks([m for m in request if m.role != "system"])
        check(
            "steering between provider and tool execution follows the complete result block",
            request[-1].role == "user"
            and "new instruction" in request[-1].content
            and [m.tool_call_id for m in request if m.role == "tool"] == ["one", "two"],
        )
        # The model reads the supersession in words (failure_view), not as a machine code.
        check(
            "fresh owner steering supersedes queued tools before they execute",
            not executions
            and all(
                json.loads(m.content)["reason"] == "tool call superseded"
                for m in request
                if m.role == "tool"
            ),
        )
        context = await new_context(["large tool read"])
        fixture = ScriptedModelAdapter(
            [ModelReply(tool_calls=calls), ModelReply(text="read completed")]
        )
        services.router.factory = scripted(fixture)
        await AgentRuntime(registry, 120, 24).execute(context)
        request = fixture.requests[-1]
        # Reads run concurrently (E1), so either may start first; the next
        # provider call is bounded by the resolved window (E3), as above.
        limits = await services.router.context_limits(
            Capability.CONVERSATION, owner_id=owner, agent_id=context.agent_id
        )
        schemas = registry.definitions()
        tokens = sum(token_estimate(m, count=limits.count) for m in request) + sum(
            limits.count(t.model_dump_json()) + 64 for t in schemas
        )
        check(
            "multiple large tool outputs remain bounded before the next provider call",
            sorted(executions) == ["one", "two"]
            and [m.tool_call_id for m in request if m.role == "tool"] == ["one", "two"]
            and sum(message_size(m) for m in request)
            + sum(len(t.model_dump_json()) for t in schemas)
            <= limits.transport_chars
            and tokens <= limits.input_tokens,
        )

        context = await new_context(["first plain request"])
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aUn8AAAAASUVORK5CYII="
        )
        key = owner + "/steering-image.png"
        path = settings.artifact_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        async with rt.db.sessions() as session, session.begin():
            artifact = ArtifactRow(
                owner_id=owner,
                thread_id=context.thread_id,
                payload={"key": key, "name": "steering-image.png", "media_type": "image/png"},
            )
            session.add(artifact)
            await session.flush()
            artifact_id = artifact.id
        await req(
            "PUT",
            "/settings/models",
            {
                "mode": "custom",
                "unified": None,
                "routes": {
                    "conversation": {"provider": "openai", "model": "explicit-text"},
                    "vision": {"provider": "openai", "model": "explicit-vision"},
                },
            },
        )
        entered = asyncio.Event()
        release = asyncio.Event()
        fixture = ScriptedModelAdapter(
            [
                ModelReply(text="obsolete text-only answer"),
                ModelReply(text="followed the steering image"),
            ]
        )
        services.router.factory = scripted(fixture)
        original_complete = fixture.complete
        first_call = True

        async def complete(*args: Any, **kwargs: Any) -> ModelReply:
            nonlocal first_call
            if first_call:
                first_call = False
                entered.set()
                await release.wait()
            return await original_complete(*args, **kwargs)

        fixture.complete = complete
        task = asyncio.create_task(AgentRuntime(load_tools(), 120, 24).execute(context))
        await asyncio.wait_for(entered.wait(), 5)
        await req(
            "POST",
            f"/threads/{context.thread_id}/messages",
            {"content": "read the newly attached image", "attachment_ids": [artifact_id]},
            202,
        )
        release.set()
        await asyncio.wait_for(task, 10)
        async with rt.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
        check(
            "steering attachments enter the same context and use the global vision route",
            run.status == "completed"
            and run.model_metadata["model"] == "explicit-vision"
            and any(m.images for m in fixture.requests[-1]),
        )
        await req(
            "PUT",
            "/settings/models",
            {
                "mode": "unified",
                "unified": {"provider": "openai", "model": "explicit-fixture"},
                "routes": {},
            },
        )

        context = await new_context(["need a timeframe"])
        entered = asyncio.Event()
        release = asyncio.Event()

        async def waiting(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
            entered.set()
            await release.wait()
            return {"_runtime_wait": True, "question": "Which timeframe?"}

        registry = ToolRegistry(
            [Tool("fixture_wait", "Explicit waiting fixture", EmptyArguments, waiting)]
            + skill_tool_stubs
        )
        fixture = ScriptedModelAdapter(
            [
                ModelReply(tool_calls=[ToolCall(id="wait", name="fixture_wait", arguments={})]),
                ModelReply(text="used the already supplied timeframe"),
            ]
        )
        services.router.factory = scripted(fixture)
        task = asyncio.create_task(AgentRuntime(registry, 120, 24).execute(context))
        await asyncio.wait_for(entered.wait(), 5)
        await req(
            "POST",
            f"/threads/{context.thread_id}/messages",
            {"content": "use one hour; I am answering before waiting commits"},
            202,
        )
        release.set()
        await asyncio.wait_for(task, 10)
        async with rt.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
        check(
            "an early answer cannot strand the run in waiting_input",
            run.status == "completed" and run.result == "used the already supplied timeframe",
        )
        await services.close()
    await rt.db.close()
    print("Persistence regression checks passed:", len(PASSED), flush=True)


if __name__ == "__main__":
    if not (make_url(os.environ.get("LONORA_DATABASE_URL", "")).database or "").endswith(
        ("_test", "_verify", "_ci")
    ):
        raise SystemExit("Set LONORA_DATABASE_URL to a disposable, migrated *_test database.")
    # The persistence checks sign in as the owner the runtime check creates.
    asyncio.run(verify_runtime())
    asyncio.run(verify_persistence())
