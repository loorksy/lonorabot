"""The acceptance run: the scenario bank on the real tools and a fake broker.

``--live`` runs each scenario as the owner's Personal Agent through Lonora's own path
(prompt assembly, model router, provider adapter, tool loop: ``execute_run`` with the worker's
production lease and round limits) on a real model, each on its own copy of a disposable
PostgreSQL database. It follows genui_eval and reuses its runner machinery, but every tool
handler is the real one, so a scenario's effects are real rows and real calls on the fake
MetaApi terminal of broker.py. No broker is reached and no order exists outside this
process. The provider key is never read here: the stored credential is the placeholder
``proxy-injected`` and the network proxy adds the real key for api.openai.com.

``--probe`` uses no model: it sends each scenario's ideal tool calls through the loop's own
dispatch and classification in the scenario's seeded state (the structural layer).

    LONORA_DATABASE_URL=postgresql+asyncpg://.../agent_eval_test \\
    .venv/bin/python scripts/agent_eval/run.py --live [--scenarios M09,M34] [--baseline]
    .venv/bin/python scripts/agent_eval/run.py --probe [--json] [--baseline]

A live run writes one scrubbed JSON line per scenario. A full run is a recording,
tests/fixtures/agent_eval/recordings/<model>-<YYYYMMDD>.jsonl; chosen scenarios are a partial
run and stay in .runtime/agent_eval/. With --baseline a full run is recordings/baseline.jsonl
and the verdicts are written to BASELINE.json, the list the test suite holds strictly.
Refuses to call a model without --live: every live run spends real model tokens.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import AsyncMock
from uuid import uuid4

from lonora_adapter_kit.types import ToolCall
from lonora_agent.environment import observe
from lonora_agent.executor import execute_run
from lonora_agent.tool_dispatch import dispatch_call
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow, RunRow
from lonora_providers.registry import model_adapter
from lonora_tools.base import ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import BRIDGE_TOOLS, ToolRegistry
from lonora_voice.voice_notes import transcribe_pending
from sqlalchemy import select
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.agent_eval import bank, broker, score  # noqa: E402
from scripts.genui_eval import run as genui  # noqa: E402

OUT = ROOT / ".runtime/agent_eval"
RECORDINGS = bank.FIXTURES / "recordings"
RESULT_CHARS = 6000
WORKER_PICKUPS = 3
MODEL = "openai/gpt-5.4-mini"  # the cheap model genui_eval uses


class RecordingRegistry(ToolRegistry):
    """Today's registry with every real handler kept and every call and outcome recorded."""

    def __init__(self, calls: list[dict[str, Any]]):
        real = load_tools().tools
        super().__init__([tool for name, tool in real.items() if name not in BRIDGE_TOOLS])
        self.calls = calls

    async def execute(
        self, call: ToolCall, context: ToolContext, scope: ToolScope = "full"
    ) -> dict[str, Any]:
        record: dict[str, Any] = {"tool": call.name, "call_id": call.id}
        record["arguments"] = json.loads(json.dumps(call.arguments, default=str))
        self.calls.append(record)
        try:
            result = await super().execute(call, context, scope)
        except LonoraError as error:
            record["error"] = error.code
            raise
        except Exception as error:
            record["error"] = type(error).__name__
            raise
        record["result"] = bounded(result)
        return result


def bounded(result: dict[str, Any]) -> dict[str, Any]:
    """A result as the recording keeps it: whole when small, otherwise its plain fields."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) <= RESULT_CHARS:
        return json.loads(text)
    return {k: v for k, v in result.items() if isinstance(v, str | int | float | bool | None)}


def clipped(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The request's transcript with long tool results cut: evidence, not a replay source."""
    return [
        {**m, "content": m["content"][:RESULT_CHARS]}
        if m.get("role") == "tool" and isinstance(m.get("content"), str)
        else m
        for m in messages
    ]


class Speech:
    """The transcription provider for a voice scenario: a short clip with no language hint
    is guessed wrong (the owner's note came back as Turkish); with the owner's language it
    is heard as he said it."""

    voice: ClassVar[dict[str, str]] = {}

    def __init__(self, api_key: str):
        del api_key

    async def transcribe(
        self,
        audio: bytes,
        model: str,
        *,
        media_type: str = "audio/wav",
        language: str | None = None,
    ) -> str:
        del audio, model, media_type
        return self.voice["heard" if (language or "").startswith("ar") else "misheard"]


async def send(api: Any, ids: dict[str, str], scenario: dict[str, Any]) -> str:
    """The owner's message (typed, or a voice note through the Gateway's own step): its Run."""
    path = f"/threads/{ids['thread_id']}/messages"
    if "voice" not in scenario:
        return (await api.request("POST", path, {"content": scenario["message"]}))["run_ids"][0]
    upload = await api.client.post(
        "/api/artifacts/upload",
        files={"file": ("note.webm", b"agent-eval-voice-note", "audio/webm;codecs=opus")},
        data={"thread_id": ids["thread_id"]},
    )
    voice = {"artifact_id": upload.json()["id"], "duration": 5.0, "peaks": [10] * 44}
    await api.request("POST", path, {"client_nonce": uuid4().hex, "voice": voice})
    Speech.voice = scenario["voice"]
    await transcribe_pending(
        api.runtime.db,
        cast(Any, SimpleNamespace(resolve=AsyncMock(return_value="proxy-injected"))),
        api.owner,
        api.settings.artifact_root,
        Speech,
    )
    async with api.runtime.db.sessions() as session:
        run = await session.scalar(
            select(RunRow)
            .where(RunRow.thread_id == ids["thread_id"], RunRow.status == "queued")
            .order_by(RunRow.created_at.desc())
        )
        assert run is not None
        return run.id


class AnyModel(genui.RecordingAdapter):
    """The recording adapter for a turn whose model the product chooses itself."""

    async def complete(self, model: str, *args: Any, **kwargs: Any) -> Any:
        self.model = model
        return await super().complete(model, *args, **kwargs)


def recording_factory(model: str | None, log: list[dict[str, Any]], origin: float) -> Any:
    if model is not None:
        return genui.recording_factory(model, log, origin)

    def factory(provider: str, secret: str) -> Any:
        return AnyModel(model_adapter(provider, secret), "", log, origin)

    return factory


async def probe(
    context: ToolContext, registry: ToolRegistry, calls: list[dict[str, Any]], steps: list[Any]
) -> None:
    """The scenario's ideal tool calls with no model, through the loop's own dispatch and
    classification: what the model would be answered."""
    state: dict[str, Any] = {"instruction_skill_ids": []}
    for step in steps:
        call = ToolCall(id=uuid4().hex, name=step["tool"], arguments=step["arguments"])
        result = await dispatch_call(
            context, registry, state, call, "full", interrupted=False, before_effect=None
        )
        observe(state, call, registry.tools.get(call.name), result)
        record = next((item for item in calls if item["call_id"] == call.id), None)
        if record is None:
            record = {"tool": call.name, "call_id": call.id, "arguments": step["arguments"]}
            calls.append(record)
        record["result"] = bounded(result)
        if result.get("ok") is False:
            record["error"] = result.get("code")


async def run_case(
    base: URL, ids: dict[str, str], scenario: dict[str, Any], model: str | None
) -> dict[str, Any]:
    """One scenario on its own copy of the template; ``model`` None runs its probe instead."""
    clone = base.set(database=f"aerun_{uuid4().hex[:12]}_test")
    await genui.admin(base, f'CREATE DATABASE "{clone.database}" TEMPLATE "{base.database}"')
    log: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    fake = bank.terminal(scenario)
    run_id, status, error_code, owner_message = "", "timeout", None, ""
    transcript: list[dict[str, Any]] = []
    replies: list[str] = []
    rich: list[Any] = []
    after: dict[str, Any] = {}
    with broker.installed(fake):
        api = genui.Api(clone)
        started = time.monotonic()
        try:
            await api.login()
            names = await bank.prepare(api, ids, scenario)
            bank.arm(fake, scenario, probe=model is None)
            started = time.monotonic()
            run_id = await send(api, ids, scenario)
            registry = RecordingRegistry(calls)

            async def leased() -> ToolContext:
                return api.runtime.services(api.owner).tool_context(
                    ids["lonora_id"],
                    ids["thread_id"],
                    await genui.lease(api, run_id),
                    api.settings.artifact_root,
                )

            if model is None:
                names |= {"$account": ids["account_id"], "$position": str(fake.tickets)}
                steps = json.loads(
                    re.sub(
                        r"\$\w+",
                        lambda m: names.get(m[0], m[0]),
                        json.dumps(scenario["probe"]["calls"], ensure_ascii=False),
                    )
                )
                await probe(await leased(), registry, calls, steps)
                status = "probe"
            else:
                # With no routing saved the product picks the model: record whichever it is.
                chosen = None if scenario["state"].get("model_routing") == "unset" else model
                factory = recording_factory(chosen, log, started)
                async with asyncio.timeout(genui.CASE_SECONDS):
                    # The loop requeues a turn for a read retry; the worker picks it up again.
                    for _ in range(WORKER_PICKUPS):
                        context = await leased()
                        context.router.factory = factory
                        await execute_run(
                            context, registry, genui.LEASE_SECONDS, genui.MAXIMUM_ROUNDS
                        )
                        async with api.runtime.db.sessions() as session:
                            if (
                                await session.scalar(
                                    select(RunRow.status).where(RunRow.id == run_id)
                                )
                                != "queued"
                            ):
                                break
            async with api.runtime.db.sessions() as session:
                row = await session.get(RunRow, run_id)
                assert row is not None
                if model is not None:
                    status, error_code = row.status, row.error_code
                transcript = genui.current_request(row.execution_state.get("messages", []))
                thread = list(
                    await session.scalars(
                        select(MessageRow)
                        .where(MessageRow.thread_id == ids["thread_id"])
                        .order_by(MessageRow.seq)
                    )
                )
                asked = max(index for index, m in enumerate(thread) if m.role == "user")
                owner_message = thread[asked].content
                answers = [m for m in thread[asked + 1 :] if m.role == "assistant"]
                replies = [m.content for m in answers]
                rich = [m.rich_content for m in answers]
        except TimeoutError:
            pass
        finally:
            turn_ms = round((time.monotonic() - started) * 1000)
            fake.faults.clear()
            after = await bank.state_after(api, ids, fake)
            await api.close()
            await genui.admin(base, f'DROP DATABASE IF EXISTS "{clone.database}" WITH (FORCE)')
    record = {
        "scenario": scenario["id"],
        "model": model,
        "status": status,
        "error_code": error_code,
        "owner_message": owner_message,
        "replies": replies,
        "rich": rich,
        "rounds": len(log),
        "tool_calls": calls,
        "state_after": after,
        "broker_calls": fake.calls,
        "transcript": clipped(transcript),
        "requests": [
            {k: v for k, v in entry.items() if k in {"latency_ms", "usage", "error", "tool_calls"}}
            for entry in log
        ],
        "reply_tool_calls": log[-1].get("tool_calls", []) if log else [],
        "usage": {
            key: sum(entry.get("usage", {}).get(key, 0) for entry in log)
            for key in ("input_tokens", "output_tokens", "cached_tokens")
        },
        "latency_ms": turn_ms,
    }
    identities = {**ids, "owner_id": api.owner, "run_id": run_id}
    return genui.scrub(record, {role: value for role, value in identities.items() if value})


async def template(base: URL, model: str) -> dict[str, str]:
    """The seeded template database every scenario is copied from."""
    await genui.admin(base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')
    await genui.admin(base, f'CREATE DATABASE "{base.database}"')
    environment = {**os.environ, "LONORA_DATABASE_URL": base.render_as_string(hide_password=False)}
    migrate = await asyncio.create_subprocess_exec(
        str(ROOT / "scripts/migrate.sh"), env=environment
    )
    if await migrate.wait():
        raise SystemExit("Migration of the seed database failed.")
    os.environ["LONORA_UI_TEST_PASSWORD"] = genui.OWNER["password"]
    with broker.installed(broker.FakeTerminal(account_id=bank.ACCOUNT)):
        api = genui.Api(base)
        try:
            await api.login()
            return await bank.seed(api, model)
        finally:
            await api.close()


async def probes(base: URL) -> list[dict[str, Any]]:
    """Every scenario's probe on a fresh template: the structural layer, no model."""
    ids = await template(base, MODEL)
    try:
        return [
            await run_case(base, ids, scenario, None)
            for scenario in bank.load().values()
            if "probe" in scenario
        ]
    finally:
        await genui.admin(base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')


async def main(arguments: argparse.Namespace) -> int:
    base = genui.disposable(os.environ.get("LONORA_DATABASE_URL", ""))
    scenarios = bank.load()
    if arguments.probe:
        records = await probes(base)
        verdicts = {
            item["scenario"]: score.judge(scenarios[item["scenario"]], item) for item in records
        }
        if arguments.baseline:
            score.write_baseline("structural", verdicts)
        if arguments.json:
            print(json.dumps(verdicts, ensure_ascii=False, indent=1))
        else:
            print(score.report(scenarios, records, structural=True))
        return 0
    chosen = (
        [scenarios[name] for name in arguments.scenarios.split(",")]
        if arguments.scenarios
        else list(scenarios.values())
    )
    now = datetime.now(UTC)
    name = arguments.model.replace("/", "-")
    path = (
        OUT / f"{name}-{now:%Y%m%dT%H%M%SZ}.jsonl"
        if arguments.scenarios
        else RECORDINGS / ("baseline.jsonl" if arguments.baseline else f"{name}-{now:%Y%m%d}.jsonl")
    )
    ids = await template(base, arguments.model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    records: list[dict[str, Any]] = []
    try:
        for scenario in chosen:
            record = await run_case(base, ids, scenario, arguments.model)
            records.append(record)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            failed = score.judge(scenario, record)
            usage = record["usage"]
            print(
                f"{scenario['id']:<13} {record['status']:<13} rounds {record['rounds']:<2} "
                f"input {usage['input_tokens']} output {usage['output_tokens']} "
                f"{record['latency_ms']} ms  {'PASS' if not failed else 'FAIL ' + ', '.join(failed)}",
                flush=True,
            )
    finally:
        await genui.admin(base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')
    total = {
        key: sum(record["usage"][key] for record in records)
        for key in ("input_tokens", "cached_tokens", "output_tokens")
    }
    print("total", json.dumps(total), "->", path)
    if arguments.baseline and not arguments.scenarios:
        score.write_baseline(
            "live",
            {item["scenario"]: score.judge(scenarios[item["scenario"]], item) for item in records},
            recording=str(path.relative_to(bank.FIXTURES)),
            model=arguments.model,
            recorded=f"{now:%Y-%m-%d}",
        )
    print(score.report(scenarios, records))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live acceptance run of the scenario bank.")
    parser.add_argument("--live", action="store_true", help="required: spends real model tokens")
    parser.add_argument("--model", default=MODEL, help="provider/model")
    parser.add_argument("--scenarios", default="", help="comma-separated scenario ids")
    parser.add_argument(
        "--baseline", action="store_true", help="record recordings/baseline.jsonl (main today)"
    )
    parser.add_argument(
        "--probe", action="store_true", help="no model: run every scenario's structural probe"
    )
    parser.add_argument("--json", action="store_true", help="with --probe: print the verdicts")
    options = parser.parse_args()
    if not options.live and not options.probe:
        parser.error("refusing to call a real model without --live (or use --probe)")
    sys.exit(asyncio.run(main(options)))
