"""Live G0 decision-eval run: today's Lonora turn on a real model, every tool from the bank.

Report-only (GENUI_PARITY_PLAN §10.6). Each case runs through Lonora's own prompt
assembly, model router, provider adapter and tool loop (``execute_run`` with the
production lease and round limits) as the owner's Personal Agent, on its own copy of a
disposable PostgreSQL database seeded by this script. Tools are answered from
tests/fixtures/genui_decision/tool_bank.json (see bank.py): no broker, no trade, no
network except the model provider. The provider key is never read here: the credential
stored in the test database is the placeholder ``proxy-injected`` and the network proxy
adds the real key for api.openai.com.

    LONORA_DATABASE_URL=postgresql+asyncpg://.../lonora_g0_test \\
    .venv/bin/python scripts/genui_eval/run.py --live [--cases A01,K01] [--limit N] [--samples 1] \
        [--baseline]

Writes one scrubbed JSON line per case and sample. A full run is a recording,
tests/fixtures/genui_decision/recordings/<model>-<YYYYMMDD>.jsonl (with --baseline under
recordings/baseline/); a run of chosen cases is a probe and stays in .runtime/genui_eval/.
Prints tokens and the scorer's report, compared with the previous recording of the same model.
Refuses to run without --live: every run spends real model tokens.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_agent.executor import execute_run
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_api.runtime import ApiRuntime
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.runs import Lease
from lonora_db.agents import create_agent
from lonora_db.events import emit
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_providers.registry import model_adapter
from sqlalchemy import select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bank  # noqa: E402
import score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".runtime/genui_eval"
RECORDINGS = bank.FIXTURES / "recordings"
PLACEHOLDER_KEY = "proxy-injected"
# A provider key never reaches a record (the proxy adds it); a key-shaped string refuses the write.
KEY_SHAPE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
LEASE_SECONDS, MAXIMUM_ROUNDS = 120, 24  # the worker's production defaults (env.py)
CASE_SECONDS = 300
OWNER = {"email": "g0-eval@example.com", "password": "g0-eval-" + uuid4().hex}
PROFILE = (
    "الاسم: المالك\nاللغة: العربية\n"
    "أتداول الذهب والفضة واليورو دولار على حساب تجريبي.\nأفضّل الردود المختصرة."
)
# The three other agents the cases name, bound to the simulation account where they trade.
AGENTS = {
    "gold_agent_id": ("وكيل الذهب", "XAUUSD"),
    "euro_agent_id": ("وكيل اليورو", "EURUSD"),
    "research_agent_id": ("باحث السوق", None),
}


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


async def seed(url: URL, model: str) -> dict[str, str]:
    """One template database: migrated, an Arabic owner, the model route, one simulation account."""
    provider, name = model.split("/", 1)
    await admin(url, f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
    await admin(url, f'CREATE DATABASE "{url.database}"')
    environment = {**os.environ, "LONORA_DATABASE_URL": url.render_as_string(hide_password=False)}
    migrate = await asyncio.create_subprocess_exec(
        str(ROOT / "scripts/migrate.sh"), env=environment
    )
    if await migrate.wait():
        raise SystemExit("Migration of the seed database failed.")
    api = Api(url)
    try:
        await api.login()
        await api.request("PUT", f"/providers/{provider}/credential", {"api_key": PLACEHOLDER_KEY})
        await api.request(
            "PUT",
            "/settings/models",
            {"mode": "unified", "unified": {"provider": provider, "model": name}},
        )
        profile = await api.request("GET", "/owner/profile")
        await api.request(
            "PUT", "/owner/profile", {"content": PROFILE, "version": profile["version"]}
        )
        await api.request(
            "PUT", "/owner/preferences", {"reply_language": "ar", "reach_me": profile["reach_me"]}
        )
        account = await api.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "g0-tajribi", "enabled": True},
        )
        lonora = next(a for a in await api.request("GET", "/agents") if a["role"] == "personal")
        thread = await api.request("POST", f"/agents/{lonora['id']}/conversation", {})
        ids = {"account_id": account["id"], "lonora_id": lonora["id"], "thread_id": thread["id"]}
        async with api.runtime.db.sessions() as session, session.begin():
            for key, (agent_name, symbol) in AGENTS.items():
                request = AgentCreate(
                    name=agent_name,
                    template="trading" if symbol else "research",
                    trading_account_id=account["id"] if symbol else None,
                    trading_symbol=symbol,
                )
                ids[key] = (await create_agent(session, api.owner, request)).id
        return ids
    finally:
        await api.close()


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
            if "first_card_ms" not in entry and score.card_closed_at("".join(streamed)):
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
        if "first_card_ms" not in entry and score.card_closed_at(reply.text):
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
    return json.loads(pattern.sub(lambda match: names[match[0]], text))


def output_path(model: str, *, baseline: bool, partial: bool, now: datetime) -> Path:
    """A full run is a recording (the G0 baseline under baseline/); chosen cases are a probe."""
    name = model.replace("/", "-")
    if partial:
        return OUT / f"{name}-{now:%Y%m%dT%H%M%SZ}.jsonl"
    return (RECORDINGS / "baseline" if baseline else RECORDINGS) / f"{name}-{now:%Y%m%d}.jsonl"


async def seed_context(api: Api, ids: dict[str, str], turns: Sequence[dict[str, str]]) -> None:
    """Earlier turns as v1 history holds them: owner text and the assistant's stored content."""
    async with api.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, ids["thread_id"], with_for_update=True)
        assert thread is not None
        for turn in turns:
            session.add(
                MessageRow(
                    thread_id=thread.id,
                    agent_id=ids["lonora_id"] if turn["role"] == "assistant" else None,
                    seq=thread.next_seq,
                    role=turn["role"],
                    content=turn["content"],
                )
            )
            thread.next_seq += 1


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


async def run_case(
    base: URL,
    template: str,
    ids: dict[str, str],
    case: dict[str, Any],
    sample: int,
    model: str,
    contexts: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    clone = base.set(database=f"g0run_{uuid4().hex[:12]}_test")
    await admin(base, f'CREATE DATABASE "{clone.database}" TEMPLATE "{template}"')
    log: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    started = time.monotonic()
    run_id = ""
    api = Api(clone)
    try:
        await api.login()
        await seed_context(api, ids, contexts.get(case["context"].get("seed") or "", []))
        # The turn: from the owner's message to the end of the run, without database setup.
        started = time.monotonic()
        sent = await api.request(
            "POST", f"/threads/{ids['thread_id']}/messages", {"content": case["message"]}
        )
        run_id = sent["run_ids"][0]
        context = api.runtime.services(api.owner).tool_context(
            ids["lonora_id"], ids["thread_id"], await lease(api, run_id), api.settings.artifact_root
        )
        context.router.factory = recording_factory(model, log, started)
        tools = bank.for_context(
            bank.materialize(bank.load_bank(), ids, datetime.now(UTC)),
            case["context"].get("seed"),
        )
        async with asyncio.timeout(CASE_SECONDS):
            await execute_run(
                context, bank.fixture_registry(tools, calls), LEASE_SECONDS, MAXIMUM_ROUNDS
            )
        turn_ms = round((time.monotonic() - started) * 1000)
        async with api.runtime.db.sessions() as session:
            row = await session.get(RunRow, run_id)
            assert row is not None
            answer = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == ids["thread_id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            status, error_code = row.status, row.error_code
            transcript = current_request(row.execution_state.get("messages", []))
            exposure = row.execution_state.get("tool_exposure")
    except TimeoutError:
        turn_ms = round((time.monotonic() - started) * 1000)
        status, error_code, transcript, answer, exposure = "timeout", None, [], None, None
    finally:
        await api.close()
        await admin(base, f'DROP DATABASE IF EXISTS "{clone.database}" WITH (FORCE)')
    usage = {
        key: sum(entry.get("usage", {}).get(key, 0) for entry in log)
        for key in ("input_tokens", "output_tokens", "cached_tokens")
    }
    last = log[-1] if log else {}
    record = {
        "case": case["id"],
        "sample": sample,
        "model": model,
        "prompt_hash": score.prompt_hash(),
        "status": status,
        "error_code": error_code,
        "reply": last.get("raw_text", ""),
        "reply_tool_calls": last.get("tool_calls", []),
        "transcript": transcript,
        "requests": log,
        "tool_calls": calls,
        "tool_exposure": exposure,
        "usage": usage,
        "latency_ms": turn_ms,
        "content": answer.content if answer and status == "completed" else None,
        "rich_content": answer.rich_content if answer and status == "completed" else None,
    }
    identities = {**ids, "owner_id": api.owner, "run_id": run_id}
    return scrub(record, {role: value for role, value in identities.items() if value})


async def main(arguments: argparse.Namespace) -> int:
    base = disposable(os.environ.get("LONORA_DATABASE_URL", ""))
    cases = score.load_cases()
    chosen = (
        [cases[name] for name in arguments.cases.split(",")]
        if arguments.cases
        else list(cases.values())
    )
    chosen = chosen[: arguments.limit] if arguments.limit else chosen
    contexts: dict[str, list[dict[str, str]]] = json.loads(
        (bank.FIXTURES / "contexts.json").read_text()
    )
    ids = await seed(base, arguments.model)
    partial = bool(arguments.cases or arguments.limit)
    path = output_path(
        arguments.model, baseline=arguments.baseline, partial=partial, now=datetime.now(UTC)
    )
    previous = None if partial else score.previous_recording(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")  # a second full run on the same day replaces that day's recording
    records: list[dict[str, Any]] = []
    try:
        for case in chosen:
            for sample in range(1, arguments.samples + 1):
                record = await run_case(
                    base, str(base.database), ids, case, sample, arguments.model, contexts
                )
                observed = await score.observe(record, case) if record["transcript"] else None
                record["observed"] = observed
                records.append(record)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                u = record["usage"]
                print(
                    f"{case['id']}#{sample} {record['status']:<13} expected {case['shape']:<2} "
                    f"observed {observed['shape'] if observed else '-':<2} "
                    f"requests {len(record['requests'])} input {u['input_tokens']} "
                    f"cached {u['cached_tokens']} output {u['output_tokens']} "
                    f"{record['latency_ms']} ms",
                    flush=True,
                )
    finally:
        await admin(base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')
    total = {
        k: sum(r["usage"][k] for r in records)
        for k in ("input_tokens", "cached_tokens", "output_tokens")
    }
    print("total", json.dumps(total), "->", path)
    if previous is not None:
        print("compared with", previous)
    earlier = score.load_results(previous) if previous else None
    print(score.report(await score.score(records, cases, earlier)))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="G0 live decision evaluation (report-only).")
    parser.add_argument("--live", action="store_true", help="required: spends real model tokens")
    parser.add_argument("--model", default="openai/gpt-5.4-mini", help="provider/model")
    parser.add_argument("--cases", default="", help="comma-separated case ids, e.g. A01,K01")
    parser.add_argument("--limit", type=int, default=0, help="run at most this many cases")
    parser.add_argument("--samples", type=int, default=1, help="samples per case (plan: 3)")
    parser.add_argument(
        "--baseline", action="store_true", help="G0: record under recordings/baseline/"
    )
    options = parser.parse_args()
    if not options.live:
        parser.error("refusing to call a real model without --live")
    sys.exit(asyncio.run(main(options)))
