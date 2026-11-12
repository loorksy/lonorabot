"""The live-run machinery of the agent evaluation (scripts/agent_eval/run.py): the real API
in-process on a disposable PostgreSQL database, a recording model adapter, the lease and the
scrubber. No provider key is read here: the network proxy adds it."""

import json
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import httpx
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_agent.visual_response import END, visual_start
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_api.runtime import ApiRuntime
from lonora_contracts.domain import utcnow
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.runs import Lease
from lonora_db.events import emit
from lonora_db.schema import RunRow
from lonora_providers.registry import model_adapter
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

# A provider key never reaches a record (the proxy adds it); a key-shaped string refuses the write.
KEY_SHAPE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
LEASE_SECONDS, MAXIMUM_ROUNDS = 120, 24  # the worker's production defaults (env.py)
CASE_SECONDS = 300
OWNER = {"email": "agent-eval@example.com", "password": "agent-eval-" + os.urandom(16).hex()}


def card_closed_at(text: str) -> int | None:
    """Where the reply's lonora-ui card closes: a card shows once its fence is complete."""
    match = visual_start(text)
    closing = END.search(text, match.end()) if match else None
    return closing.end() if closing else None


def disposable(url: str) -> URL:
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql") or not (parsed.database or "").endswith(
        ("_test", "_verify", "_ci")
    ):
        raise SystemExit("Set LONORA_DATABASE_URL to a disposable PostgreSQL *_test database.")
    return parsed


async def admin(base: URL, *statements: str) -> None:
    engine = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


class Api:
    """The real API app in-process for one database (no worker, no background run)."""

    def __init__(self, url: URL):
        os.environ["LONORA_DATABASE_URL"] = url.render_as_string(hide_password=False)
        get_settings.cache_clear()
        self.settings = get_settings()
        self.app = create_app(self.settings)
        self.runtime = cast(ApiRuntime, self.app.state.runtime)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app), base_url="https://g0-eval.test"
        )
        self.owner = ""

    async def request(self, method: str, path: str, body: Any = None) -> Any:
        response = await self.client.request(method, "/api" + path, json=body)
        if not response.is_success:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
        return response.json()

    async def login(self) -> None:
        if not (await self.request("GET", "/onboarding"))["owner_initialized"]:
            token = self.settings.bootstrap_token.get_secret_value()
            await self.request("POST", "/onboarding", {**OWNER, "bootstrap_token": token})
        login = await self.request("POST", "/auth/login", OWNER)
        self.client.headers["X-CSRF-Token"] = login["csrf"]
        self.owner = login["owner"]["id"]

    async def close(self) -> None:
        await self.client.aclose()
        await self.runtime.close()


class RecordingAdapter:
    """The real provider adapter; records the exact admitted request and the raw reply."""

    def __init__(self, inner: ModelAdapter, model: str, log: list[dict[str, Any]], origin: float):
        self.inner, self.model, self.log, self.origin = inner, model, log, origin

    def since_origin(self) -> int:
        """Milliseconds since the owner's message (the turn's start)."""
        return round((time.monotonic() - self.origin) * 1000)

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply:
        if model != self.model:
            raise SystemExit(f"Refusing an unexpected model: {model}")
        started = time.monotonic()
        entry: dict[str, Any] = {"messages": len(messages), "tools": [t.name for t in tools]}
        entry["max_output_tokens"] = max_output_tokens
        self.log.append(entry)
        streamed: list[str] = []

        async def delta(chunk: str) -> None:
            # v1 shows a card once its frame is complete: that is the first card line's moment.
            streamed.append(chunk)
            if "first_card_ms" not in entry and card_closed_at("".join(streamed)):
                entry["first_card_ms"] = self.since_origin()
            assert on_delta is not None
            await on_delta(chunk)

        try:
            reply = await self.inner.complete(
                model,
                messages,
                tools,
                max_output_tokens=max_output_tokens,
                on_delta=None if on_delta is None else delta,
            )
        except BaseException as error:
            entry["error"] = type(error).__name__
            raise
        finally:
            entry["latency_ms"] = round((time.monotonic() - started) * 1000)
        if "first_card_ms" not in entry and card_closed_at(reply.text):
            entry["first_card_ms"] = self.since_origin()  # a reply that was not streamed
        entry["raw_text"] = reply.text
        entry["tool_calls"] = [call.model_dump(mode="json") for call in reply.tool_calls]
        entry["usage"] = reply.usage.model_dump(mode="json")
        return reply

    async def discover(self) -> list[ModelDescriptor]:
        return await self.inner.discover()

    async def close(self) -> None:
        await self.inner.close()


def recording_factory(
    model: str, log: list[dict[str, Any]], origin: float
) -> Callable[[str, str], ModelAdapter]:
    provider, name = model.split("/", 1)

    def factory(selected: str, secret: str) -> ModelAdapter:
        if selected != provider:
            raise SystemExit(f"Refusing an unexpected provider: {selected}")
        return RecordingAdapter(model_adapter(selected, secret), name, log, origin)

    return factory


def scrub(record: dict[str, Any], identities: Mapping[str, str]) -> dict[str, Any]:
    """The record without the ids that differ per run, and never with a key (§10.6).

    Seeded rows (owner, agents, thread, account, run) become fixed UUIDs named after their role
    and provider call ids become call_1, call_2, ... in order of appearance. Each is replaced
    everywhere at once, so a replay still resolves every fact against its call.
    """
    text = json.dumps(record, ensure_ascii=False)
    if KEY_SHAPE.search(text):
        raise SystemExit("Refusing to write a record that holds a key-shaped string.")
    calls = [
        *(c["id"] for m in record["transcript"] for c in m.get("tool_calls", [])),
        *(c["id"] for r in record["requests"] for c in r.get("tool_calls", [])),
        *(c["id"] for c in record["reply_tool_calls"]),
        *(c.get("call_id") for c in record["tool_calls"]),
    ]
    names = {old: f"call_{n}" for n, old in enumerate(dict.fromkeys(c for c in calls if c), 1)}
    names.update(
        {
            old: str(uuid5(NAMESPACE_URL, "lonora-g0-eval/" + role))
            for role, old in identities.items()
        }
    )
    if not names:
        return record
    pattern = re.compile("|".join(map(re.escape, sorted(names, key=len, reverse=True))))
    text = pattern.sub(lambda match: names[match[0]], text)
    # A trade request's operation_id is new on every run (TradeRequest's default).
    operations: dict[str, str] = {}
    text = re.sub(
        r'(\\?"operation_id\\?":\s*\\?")([^"\\]+)',
        lambda m: m[1] + operations.setdefault(m[2], f"operation_{len(operations) + 1}"),
        text,
    )
    return json.loads(text)


async def lease(api: Api, run_id: str) -> Lease:
    async with api.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
        assert row is not None
        row.status, row.lease_owner = "running", "g0-eval"
        row.lease_fence += 1
        row.lease_expires_at = utcnow() + timedelta(seconds=LEASE_SECONDS)
        emit(
            session,
            api.owner,
            "run.running",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
        )
        return Lease(run_id=row.id, owner="g0-eval", fence=row.lease_fence)


def current_request(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The run's transcript from the owner's message on (what the projector uses as evidence)."""
    starts = [
        index
        for index, message in enumerate(messages)
        if message["role"] == "user"
        and message.get("context_origin", "conversation") == "conversation"
    ]
    return messages[starts[-1] :] if starts else messages
