"""Real disposable-PostgreSQL reply/peer checks and explicitly scripted browser fixtures."""

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import httpx
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_agent.collaboration.outcome_return import return_outcome, return_pending_outcomes
from lonora_agent.collaboration.peer_messages import delegate_peer
from lonora_agent.context.builder import build_context
from lonora_agent.model_runtime import model_turn
from lonora_agent.progress import progress
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_api.runtime import ApiRuntime
from lonora_contracts.domain import MessageCreate, utcnow
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.events import emit, events_after
from lonora_db.messages import send_message
from lonora_db.runs import complete_run
from lonora_db.schema import MessageRow, PeerMessageRow, RunRow, SteeringRow
from lonora_db.streaming import MAX_STREAM_CHARS
from lonora_providers.router import GlobalModelRouter
from lonora_tools.context import ToolContext
from sqlalchemy import func, select
from sqlalchemy.engine import make_url


def test_settings():
    explicit = os.environ.get("LONORA_DATABASE_URL", "")
    url = make_url(explicit)
    if (
        not url.drivername.startswith("postgresql")
        or not (url.database or "").endswith(("_test", "_verify", "_ci"))
        or {"database", "dbname"}.intersection(key.lower() for key in url.query)
    ):
        raise SystemExit("Set an explicit disposable PostgreSQL *_test, *_verify or *_ci database.")
    return get_settings()


class Fixture:
    def __init__(self):
        self.settings = test_settings()
        self.app = create_app(self.settings)
        self.runtime = cast(ApiRuntime, self.app.state.runtime)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app), base_url="https://streaming.test"
        )
        self.owner = ""
        self.agents: list[str] = []
        self.groups: list[str] = []
        self.group_threads: list[str] = []

    async def open(self):
        credentials = {
            "email": os.environ.get("LONORA_UI_TEST_EMAIL", "ci@example.com"),
            "password": os.environ.get("LONORA_UI_TEST_PASSWORD", "ci-only-owner-password"),
        }
        status = await self.request("GET", "/onboarding")
        if not status["owner_initialized"]:
            await self.request(
                "POST",
                "/onboarding",
                {
                    **credentials,
                    "bootstrap_token": self.settings.bootstrap_token.get_secret_value(),
                },
            )
        login = await self.request("POST", "/auth/login", credentials)
        self.client.headers["X-CSRF-Token"] = login["csrf"]
        self.owner = login["owner"]["id"]
        return self

    async def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self.client.request(method, "/api" + path, json=body)
        assert response.is_success, f"{method} {path}: HTTP {response.status_code}"
        return response.json()

    async def agent(self, name: str) -> dict[str, Any]:
        # Legacy unbound fixture identities model migrated agents. Production
        # POST /agents requires a real, owner-selected broker market.
        from lonora_contracts.domain import AgentCreate
        from lonora_db.agents import agent_data, create_agent

        async with self.runtime.db.sessions() as session, session.begin():
            row = agent_data(
                await create_agent(
                    session, self.owner, AgentCreate(name=name + " " + uuid4().hex[:8])
                )
            )
        self.agents.append(row["id"])
        return row

    async def conversation(self, agent: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/agents/{agent['id']}/conversation", {})

    async def run(self, agent: dict[str, Any], thread: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "prompt": "Explicit scripted regression fixture",
            },
        )

    async def lease(self, run: dict[str, Any]) -> ToolContext:
        async with self.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, run["id"], with_for_update=True, populate_existing=True)
            assert row is not None
            row.status = "running"
            row.lease_owner = "scripted-streaming-fixture"
            row.lease_fence += 1
            row.lease_expires_at = utcnow() + timedelta(seconds=300)
            lease = Lease(run_id=row.id, owner="scripted-streaming-fixture", fence=row.lease_fence)
            emit(
                session,
                self.owner,
                "run.running",
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                run_id=row.id,
            )
        return self.runtime.services(self.owner).tool_context(
            run["agent_id"], run["thread_id"], lease, self.settings.artifact_root
        )

    def context(self, data: dict[str, Any]) -> ToolContext:
        run = data["run"]
        return self.runtime.services(self.owner).tool_context(
            run["agent_id"],
            run["thread_id"],
            Lease.model_validate(data["lease"]),
            self.settings.artifact_root,
        )

    async def close(self, cleanup: bool = True):
        if cleanup:
            for thread in self.group_threads:
                await self.request("DELETE", "/threads/" + thread)
            for group in self.groups:
                await self.request("DELETE", "/groups/" + group)
            for agent in self.agents:
                await self.request("DELETE", "/agents/" + agent)
        await self.client.aclose()
        await self.runtime.close()


class ScriptedRouter:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks

    async def complete(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        on_attempt: Callable[[ModelSelection], Awaitable[None]] | None = None,
    ) -> tuple[ModelReply, ModelSelection]:
        selection = ModelSelection(provider="openai", model="scripted-streaming-fixture")
        if on_attempt:
            await on_attempt(selection)
        for chunk in self.chunks:
            if on_delta:
                await on_delta(chunk)
        return ModelReply(text="".join(self.chunks)), selection


async def checks():
    fixture = await Fixture().open()
    passed: list[str] = []

    def check(name: str, ok: bool):
        assert ok, name
        passed.append(name)
        print("PASS", name, flush=True)

    try:
        a, b, c = (
            await fixture.agent("Stream sender"),
            await fixture.agent("Stream recipient"),
            await fixture.agent("Stream third agent"),
        )
        at, bt, ct = (
            await fixture.conversation(a),
            await fixture.conversation(b),
            await fixture.conversation(c),
        )
        ar = await fixture.run(a, at)
        context = await fixture.lease(ar)
        chunks = [f"chunk-{i:03}:" + "x" * 128 for i in range(170)]
        scripted = cast(GlobalModelRouter, ScriptedRouter(chunks))
        from dataclasses import replace

        await model_turn(
            replace(context, router=scripted),
            [ModelMessage(role="user", content="Explicit fixture")],
            [],
            Capability.CONVERSATION,
        )
        fresh = await fixture.request("GET", "/runs/" + ar["id"])
        stream = fresh["stream"]
        check(
            "170 deltas survive a fresh API read independently of the 150-event client window",
            stream["sequence"] == 170 and stream["text"] == "".join(chunks),
        )
        old_turn = stream["turn_id"]
        await progress(context, "run.reply_started", {"turn_id": "fallback-fixture"})
        await progress(context, "run.delta", {"turn_id": "fallback-fixture", "text": "replacement"})
        rejected = False
        try:
            await progress(context, "run.delta", {"turn_id": old_turn, "text": "stale provider"})
        except LonoraError as error:
            rejected = error.code == "stale_stream_turn"
        fresh = await fixture.request("GET", "/runs/" + ar["id"])
        check(
            "fallback generation replaces the preview and rejects the previous turn",
            rejected
            and fresh["stream"]["text"] == "replacement"
            and fresh["stream"]["generation"] > stream["generation"],
        )
        await progress(
            context,
            "run.delta",
            {"turn_id": "fallback-fixture", "text": "z" * (MAX_STREAM_CHARS + 20)},
        )
        fresh = await fixture.request("GET", "/runs/" + ar["id"])
        check(
            "durable previews are bounded without truncating the final answer",
            len(fresh["stream"]["text"]) == MAX_STREAM_CHARS and fresh["stream"]["truncated"],
        )
        replacement = await fixture.lease(ar)
        await progress(replacement, "run.reply_started", {"turn_id": "recovered-fixture"})
        await progress(
            replacement, "run.delta", {"turn_id": "recovered-fixture", "text": "recovered answer"}
        )
        stale = False
        try:
            await progress(
                context, "run.delta", {"turn_id": "fallback-fixture", "text": "late worker"}
            )
        except LonoraError as error:
            stale = error.code == "stale_lease"
        check("a replaced worker lease cannot append to the recovered stream", stale)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await complete_run(session, replacement.lease, "recovered answer", {})
        fresh = await fixture.request("GET", "/runs/" + ar["id"])
        history = cast(
            list[dict[str, Any]], await fixture.request("GET", "/threads/" + at["id"] + "/messages")
        )
        check(
            "completion identifies its exact durable message for duplicate-free handoff",
            fresh["stream"]["phase"] == "committed"
            and any(
                row["id"] == fresh["stream"]["message_id"] and row["content"] == "recovered answer"
                for row in history
            ),
        )
        async with fixture.runtime.db.sessions() as session:
            delivered = await events_after(session, fixture.owner, 0, at["id"], 500)
            check(
                "snapshot sequence is independent of publicly assigned event cursors",
                fresh["stream"]["sequence"] == 1
                and max(row.payload.get("_ln_public_cursor", 0) for row in delivered) > 170,
            )
        parent = await fixture.run(a, at)
        parent_context = await fixture.lease(parent)
        peers = await asyncio.wait_for(
            asyncio.gather(
                *(
                    delegate_peer(
                        parent_context.for_call("one-peer-intent"),
                        b["id"],
                        "Find the durable answer",
                    )
                    for _ in range(5)
                )
            ),
            10,
        )
        check(
            "concurrent retries create one peer run in the recipient's canonical conversation",
            len({row["id"] for row in peers}) == 1
            and all(row["thread_id"] == bt["id"] for row in peers),
        )
        second = await delegate_peer(
            parent_context.for_call("another-peer-intent"), b["id"], "A second distinct task"
        )
        check(
            "new peer tasks continue the same recipient conversation",
            second["thread_id"] == bt["id"],
        )
        async with fixture.runtime.db.sessions() as session:
            requests = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id.in_([at["id"], bt["id"]]),
                        MessageRow.content == "Find the durable answer",
                    )
                )
            )
        check("one peer request is visibly persisted once in each conversation", len(requests) == 2)
        child_context = await fixture.lease(peers[0])
        peer_context = await build_context(child_context)
        check(
            "a canonical peer task appears once in attributed model history",
            sum("Find the durable answer" in message.content for message in peer_context) == 1,
        )
        forbidden: list[str] = []
        for ctx, target in ((parent_context, a["id"]), (child_context, a["id"])):
            try:
                await delegate_peer(ctx.for_call("forbidden-cycle"), target, "Forbidden fixture")
            except LonoraError as error:
                forbidden.append(error.code)
        check(
            "self delegation and an ancestor communication cycle are rejected",
            forbidden == ["peer_self_target", "peer_cycle"],
        )
        br = await fixture.run(b, bt)
        bctx = await fixture.lease(br)
        reciprocal = await asyncio.wait_for(
            asyncio.gather(
                delegate_peer(parent_context.for_call("reverse-a"), b["id"], "Independent A to B"),
                delegate_peer(bctx.for_call("reverse-b"), a["id"], "Independent B to A"),
            ),
            10,
        )
        check(
            "reciprocal independent requests do not deadlock on agent FK locks",
            len(reciprocal) == 2,
        )

        async def owner_send():
            async with fixture.runtime.db.sessions() as session, session.begin():
                return await send_message(
                    session,
                    fixture.owner,
                    ct["id"],
                    MessageCreate(content="Concurrent owner direction", client_nonce=uuid4().hex),
                )

        await asyncio.wait_for(
            asyncio.gather(
                delegate_peer(
                    parent_context.for_call("owner-race"), c["id"], "Peer versus owner fixture"
                ),
                owner_send(),
            ),
            10,
        )
        check("peer delivery and a recipient owner message do not invert agent/thread locks", True)
        await progress(child_context, "run.reply_started", {"turn_id": "peer-answer"})
        await progress(
            child_context, "run.delta", {"turn_id": "peer-answer", "text": "Visible peer outcome"}
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            await complete_run(session, child_context.lease, "Visible peer outcome", {})
        await asyncio.wait_for(
            asyncio.gather(
                return_outcome(fixture.runtime.db, peers[0]["id"]),
                return_outcome(fixture.runtime.db, peers[0]["id"]),
            ),
            10,
        )
        async with fixture.runtime.db.sessions() as session:
            peer = await session.get(PeerMessageRow, peers[0]["id"])
            messages = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == at["id"],
                        MessageRow.content.contains("Visible peer outcome"),
                    )
                )
            )
            steering = await session.scalar(
                select(func.count())
                .select_from(SteeringRow)
                .where(SteeringRow.run_id == parent["id"])
            )
            check(
                "a terminal peer outcome returns once and steers its active parent",
                peer is not None
                and peer.payload["status"] == "completed"
                and len(messages) == 1
                and bool(steering),
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, parent["id"], with_for_update=True)
            assert row is not None
            row.status = "queued"
            row.execution_state = {
                "messages": [{"role": "user", "content": "Checkpointed continuation"}],
                "pending": [],
            }
        direction = await fixture.request(
            "POST",
            "/threads/" + at["id"] + "/messages",
            {"content": "Owner direction after checkpoint", "client_nonce": uuid4().hex},
        )
        async with fixture.runtime.db.sessions() as session:
            check(
                "owner direction steers a queued checkpoint instead of being lost on restore",
                await session.scalar(
                    select(func.count())
                    .select_from(SteeringRow)
                    .where(
                        SteeringRow.run_id == parent["id"],
                        SteeringRow.message_id == direction["message"]["id"],
                    )
                )
                == 1,
            )
        cancelled = await fixture.request("POST", "/runs/" + second["id"] + "/cancel", {})
        await fixture.request("POST", "/runs/" + second["id"] + "/cancel", {})
        async with fixture.runtime.db.sessions() as session:
            peer = await session.get(PeerMessageRow, second["id"])
            check(
                "a queued peer cancellation returns durably without a worker or duplicate outcome",
                cancelled["status"] == "cancelled"
                and peer is not None
                and peer.payload["status"] == "cancelled"
                and len(peer.payload["source_outcome_message_ids"]) == 1,
            )
            assert peer is not None
            check(
                "a returned peer outcome steers its queued checkpointed parent exactly once",
                await session.scalar(
                    select(func.count())
                    .select_from(SteeringRow)
                    .where(
                        SteeringRow.run_id == parent["id"],
                        SteeringRow.message_id == peer.payload["source_outcome_message_id"],
                    )
                )
                == 1,
            )
        parent_context = await fixture.lease(parent)
        recovered_child = await delegate_peer(
            parent_context.for_call("crash-window"), c["id"], "Recover a committed outcome"
        )
        recovered_context = await fixture.lease(recovered_child)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await complete_run(
                session, recovered_context.lease, "Committed before worker restart", {}
            )
        await return_pending_outcomes(fixture.runtime.db)
        await return_pending_outcomes(fixture.runtime.db)
        async with fixture.runtime.db.sessions() as session:
            peer = await session.get(PeerMessageRow, recovered_child["id"])
            check(
                "bounded maintenance repairs a completion/return crash window exactly once",
                peer is not None
                and len(peer.payload["source_outcome_message_ids"]) == 1
                and peer.payload["result"] == "Committed before worker restart",
            )
    finally:
        await fixture.close()
    print("Streaming and peer integration checks passed:", len(passed))


async def browser_action(data: dict[str, Any]):
    fixture = await Fixture().open()
    action = data["action"]
    try:
        if action == "peer_init":
            a, b = (
                await fixture.agent("Peer browser sender"),
                await fixture.agent("Peer browser recipient"),
            )
            source, target = await fixture.conversation(a), await fixture.conversation(b)
            parent = await fixture.run(a, source)
            context = await fixture.lease(parent)
            child = await delegate_peer(
                context.for_call("browser-peer"), b["id"], "PERSISTED peer request"
            )
            return {
                "agents": [a["id"], b["id"]],
                "source_thread": source["id"],
                "target_thread": target["id"],
                "child": child,
            }
        if action == "peer_complete":
            context = await fixture.lease(data["child"])
            await progress(context, "run.reply_started", {"turn_id": "browser-peer-answer"})
            await progress(
                context,
                "run.delta",
                {"turn_id": "browser-peer-answer", "text": "PERSISTED peer answer"},
            )
            async with fixture.runtime.db.sessions() as session, session.begin():
                await complete_run(session, context.lease, "PERSISTED peer answer", {})
            await return_outcome(fixture.runtime.db, context.lease.run_id)
            return {"returned": True}
        if action == "peer_cleanup":
            fixture.agents = data["agents"]
            return {"cleaned": True}
        if action == "init":
            a, b = await fixture.agent("Stream browser A"), await fixture.agent("Stream browser B")
            group = await fixture.request(
                "POST",
                "/groups/create",
                {
                    "name": "Streaming regression " + uuid4().hex[:8],
                    "member_ids": [a["id"], b["id"]],
                    "participation": "mentions_or_lead",
                },
            )
            thread = {"id": group["thread_id"]}
            if data.get("history"):
                admitted: dict[str, Any] = {}
                for index in range(105):
                    admitted = await fixture.request(
                        "POST",
                        f"/threads/{thread['id']}/messages",
                        {
                            "content": f"HISTORY {index:03} immutable fixture",
                            "client_nonce": uuid4().hex,
                        },
                    )
                for identifier in admitted["run_ids"]:
                    await fixture.request("POST", f"/runs/{identifier}/cancel", {})
            run = await fixture.run(a, thread)
            context = await fixture.lease(run)
            turn = uuid4().hex
            await progress(context, "run.reply_started", {"turn_id": turn})
            await progress(
                context, "run.delta", {"turn_id": turn, "text": "START durable browser prefix "}
            )
            return {
                "agents": [a["id"], b["id"]],
                "group": group["id"],
                "thread": thread["id"],
                "run": run,
                "lease": context.lease.model_dump(),
                "turn": turn,
                "text": "START durable browser prefix ",
            }
        if action == "cleanup":
            fixture.agents = data["agents"]
            fixture.groups = [data["group"]]
            fixture.group_threads = [data["thread"]]
            return {"cleaned": True}
        context = fixture.context(data)
        if action == "append":
            text = "".join(f"chunk-{i:03} " + "x" * 120 + " " for i in range(170))
            for i in range(170):
                await progress(
                    context,
                    "run.delta",
                    {"turn_id": data["turn"], "text": f"chunk-{i:03} " + "x" * 120 + " "},
                )
            for i in range(170):
                await progress(context, "fixture.activity", {"index": i})
            return {**data, "text": data["text"] + text}
        if action == "recover":
            context = await fixture.lease(data["run"])
            turn = uuid4().hex
            await progress(context, "run.reply_started", {"turn_id": turn})
            await progress(
                context, "run.delta", {"turn_id": turn, "text": "RECOVERED new fenced turn"}
            )
            return {
                **data,
                "lease": context.lease.model_dump(),
                "turn": turn,
                "text": "RECOVERED new fenced turn",
            }
        if action == "complete":
            async with fixture.runtime.db.sessions() as session, session.begin():
                await complete_run(session, context.lease, data["text"], {})
            return {"complete": True}
        raise ValueError("Unknown fixture action")
    finally:
        await fixture.close(cleanup=action in {"cleanup", "peer_cleanup"})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "browser":
        print(json.dumps(asyncio.run(browser_action(json.load(sys.stdin)))))
    else:
        asyncio.run(checks())
