"""The mandate's acceptance scenario (VISION.md section 16), step by step.

Each step of tests/fixtures/agent_eval/acceptance.json names the feature it needs, the
worker who owns that feature and the code that proves the feature is on this commit
(``needs``). A step whose feature is missing is *pending*: it is reported, never run and
never approximated. A step whose feature is present runs from its own seeded state, so it
passes or fails as soon as its own feature lands, whatever the state of the steps before it.

Two modes:

- ``--offline``: scripted model turns (``ScriptedModel``) through Lonora's real loop
  (``execute_run``), the real tool handlers and the real MetaApi adapter over the fake
  terminal of broker.py. No model, no network. The local gate of every PR runs it.
- ``--live``: the same steps with the product choosing and calling a real model through the
  providers saved in the database (the owner's server). The harness only presents the
  situation (a watch firing, a dropped reply); a step that depends on the model's choice
  passes when the agent acted within its authority without asking and explained in one
  line. Which choice it made is not asserted. Plumbing assertions are exact in both modes.

The harness induces what the scenario needs: a lost broker reply (the broker applied the
operation and the connection dropped before the answer), a price move, and the wakes that
follow. Nothing here reaches a broker, prints a credential or keeps a database: every step
runs on its own copy of a disposable PostgreSQL template, dropped at the end.

    LONORA_DATABASE_URL=postgresql+asyncpg://.../accept_test \\
    .venv/bin/python scripts/agent_eval/acceptance.py --offline [--steps 4c] [--json]
    .venv/bin/python scripts/agent_eval/acceptance.py --live [--steps 4c]
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.context.history import peer_content
from lonora_agent.context.routine import PEER_WAKE
from lonora_agent.environment import classify, error_class
from lonora_agent.executor import execute_run
from lonora_automation.runner import dispatch_routines
from lonora_contracts.domain import AgentCreate
from lonora_contracts.routines import RoutineCreate
from lonora_db.agents import create_agent
from lonora_db.market_watches import MarketWatchRepository
from lonora_db.owner_profile import REACH_ME_KEY
from lonora_db.peer_messages import PeerMessageRepository
from lonora_db.routines import create_routine
from lonora_db.schema import AgentRow, MessageRow, RunRow, TradingJournalRow
from lonora_db.transactions import SettingsRepository
from lonora_market.watchers import check_watches
from lonora_tools.loader import load_tools
from lonora_trading.broker_recovery import maintenance_account_recovery
from lonora_trading.morning_brief import TRIGGER, brief_tick, latest_close, owner_zone
from lonora_trading.reconciliation import reconcile_ambiguous
from lonora_trading.weekly_report import TRIGGER as REPORT_TRIGGER
from lonora_trading.weekly_report import WAKE_TEXT as REPORT_TEXT
from sqlalchemy import func, select
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.agent_eval import bank, broker  # noqa: E402
from scripts.agent_eval import run as runner  # noqa: E402
from scripts.agent_eval import runner as harness  # noqa: E402

SCENARIO = bank.FIXTURES / "acceptance.json"
# Runs the harness drives after one induced event: the wake, and the wakes it causes.
MAXIMUM_RUNS = 6


def load() -> dict[str, Any]:
    return json.loads(SCENARIO.read_text())


# --- Whether a step's feature is on this commit ------------------------------------------


def missing(needs: list[dict[str, str]]) -> list[str]:
    """What a step needs that this commit does not have (empty: the step can run)."""
    tools = set(load_tools().tools)
    absent: list[str] = []
    for need in needs:
        if "pending" in need:
            absent.append(need["pending"])
        elif "tool" in need and need["tool"] not in tools:
            absent.append(f"tool {need['tool']}")
        elif "code" in need:
            module, _, name = need["code"].partition(":")
            try:
                found = hasattr(import_module(module), name) if name else True
            except ImportError:
                found = False
            if not found:
                absent.append(need["code"])
    return absent


# --- Scripted model turns ------------------------------------------------------------------


@dataclass
class ScriptedModel:
    """The offline model: each run of an agent answers with that agent's next scripted turn.

    A turn is a list of replies, one per round: ``{"calls": [{"tool", "arguments"}]}`` or
    ``{"text": "..."}``. ``$name`` in an argument is the step's own value (an account, a
    ticket). The loop, the tool handlers and the broker adapter are the product's own.
    """

    turns: dict[str, list[list[dict[str, Any]]]]
    names: dict[str, str] = field(default_factory=dict[str, str])
    agent: str = ""
    replies: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    used: list[str] = field(default_factory=list[str])
    # What each turn's model was shown on its first round, in the order the turns ran.
    shown: list[tuple[str, list[ModelMessage]]] = field(
        default_factory=list[tuple[str, list[ModelMessage]]]
    )

    def start(self, agent: str) -> None:
        """The next run is ``agent``'s: take its next scripted turn."""
        self.agent = agent
        queue = self.turns.get(agent, [])
        if not queue:
            raise AssertionError(f"no scripted turn left for {agent}")
        self.replies = list(queue.pop(0))
        self.used.append(agent)
        self.shown.append((agent, []))

    def factory(self, provider: str, secret: str) -> "ScriptedAdapter":
        del provider, secret
        return ScriptedAdapter(self)


class ScriptedAdapter:
    def __init__(self, script: ScriptedModel):
        self.script = script

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply:
        del model, tools, max_output_tokens, on_delta
        if not self.script.shown[-1][1]:
            self.script.shown[-1][1].extend(messages)
        if not self.script.replies:
            raise AssertionError(f"{self.script.agent}'s scripted turn ended early")
        reply = self.script.replies.pop(0)
        if "text" in reply:
            return ModelReply(text=reply["text"])
        calls = [
            ToolCall(
                id=uuid4().hex,
                name=call["tool"],
                arguments=resolve(call["arguments"], self.script.names),
            )
            for call in reply["calls"]
        ]
        return ModelReply(tool_calls=calls)

    async def discover(self) -> list[Any]:
        return []

    async def close(self) -> None:
        return None


def resolve(value: Any, names: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {k: resolve(v, names) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [resolve(item, names) for item in cast(list[Any], value)]
    if isinstance(value, str):
        return re.sub(r"\$\w+", lambda m: names.get(m[0], m[0]), value)
    return value


# --- The induced broker events -------------------------------------------------------------


class AcceptanceTerminal(broker.FakeTerminal):
    """broker.py's terminal plus the one event the scenario induces on it: a lost reply.

    ``lose_reply("close_position")`` lets the next close reach the account (the position is
    closed and its deal is in history) and then drops the connection before the answer,
    which is what makes an operation's outcome unknown to the door.
    """

    lost: set[str]

    def __post_init__(self) -> None:
        super().__post_init__()
        self.lost = set()

    def lose_reply(self, method: str) -> None:
        self.lost.add(method)

    async def close_position_partially(
        self, position_id: str, volume: float | None, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        answer = await super().close_position_partially(position_id, volume, options=options)
        if "close_position" in self.lost:
            self.lost.discard("close_position")
            raise ConnectionError("MetaApi websocket client disconnected from the trading server")
        return answer

    def move(self, base: str, bid: str) -> None:
        """The market's bid is now ``bid`` (its spread is kept)."""
        self.bids[broker.broker_symbol(base, self.variant)] = Decimal(bid)


# --- Driving runs as the worker does -------------------------------------------------------


@dataclass
class Stage:
    """One step's copy of the template database, its terminal and the model it uses."""

    api: Any
    ids: dict[str, str]
    terminal: AcceptanceTerminal
    model: ScriptedModel | None
    runs: list[str] = field(default_factory=list[str])
    calls: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    # Runs the template left queued (the signed grant's account task): not the step's.
    before: set[str] = field(default_factory=set[str])
    # Each conversation's last message before the step (``seq`` counts per conversation).
    seq: dict[str, int] = field(default_factory=dict[str, int])

    async def settle(self) -> None:
        """Mark what the template left, so the step sees only what it caused."""
        async with self.api.runtime.db.sessions() as session:
            self.before = set(
                await session.scalars(select(RunRow.id).where(RunRow.status == "queued"))
            )
            self.seq = {
                thread: seq
                for thread, seq in await session.execute(
                    select(MessageRow.thread_id, func.max(MessageRow.seq)).group_by(
                        MessageRow.thread_id
                    )
                )
            }

    @property
    def brokers(self) -> Any:
        return self.api.runtime.services(self.api.owner).brokers

    async def drain(self) -> None:
        """Every queued run of the owner, oldest first, through ``execute_run``."""
        for _ in range(MAXIMUM_RUNS):
            async with self.api.runtime.db.sessions() as session:
                run = await session.scalar(
                    select(RunRow)
                    # One owner per disposable database: every queued run is the owner's.
                    .where(RunRow.status == "queued", RunRow.id.not_in(self.before))
                    .order_by(RunRow.created_at)
                )
            if run is None:
                return
            if run.id in self.runs:
                raise AssertionError(f"a run is still queued after {runner.WORKER_PICKUPS} pickups")
            self.runs.append(run.id)
            if self.model is not None:
                self.model.start(self.turn(run))
            for _ in range(runner.WORKER_PICKUPS):
                context = self.api.runtime.services(self.api.owner).tool_context(
                    run.agent_id,
                    run.thread_id,
                    await harness.lease(self.api, run.id),
                    self.api.settings.artifact_root,
                )
                if self.model is not None:
                    context.router.factory = self.model.factory
                registry = runner.RecordingRegistry(self.calls)
                async with asyncio.timeout(harness.CASE_SECONDS):
                    await execute_run(
                        context, registry, harness.LEASE_SECONDS, harness.MAXIMUM_ROUNDS
                    )
                for call in self.calls:
                    call.setdefault("agent_id", run.agent_id)
                async with self.api.runtime.db.sessions() as session:
                    ended = await session.get(RunRow, run.id, populate_existing=True)
                    assert ended is not None
                    if ended.status == "failed":
                        raise AssertionError(
                            f"{self.handle(run.agent_id)}'s run failed: {ended.error_code}"
                        )
                    if ended.status != "queued":
                        break
        raise AssertionError(f"more than {MAXIMUM_RUNS} runs after one event")

    def handle(self, agent_id: str) -> str:
        """The scenario's name for an agent (``gold``, ``euro``, ...)."""
        keys: list[str] = list(self.model.turns) if self.model is not None else []
        # A plain key names the agent of an ordinary wake; a keyed one only its trigger's.
        scripted = [key for key in keys if "@" not in key]
        scripted += [key.split("@")[0] for key in keys if "@" in key]
        known = [*scripted, "gold", "lonora_id"]
        return next((k for k in known if self.ids.get(k) == agent_id), "an agent")

    def turn(self, run: RunRow) -> str:
        """Whose scripted turn answers ``run``: ``name@trigger`` when the script keys the
        agent's turns by what woke it (a brief, a report), else the agent's name."""
        keys: list[str] = list(self.model.turns) if self.model is not None else []
        for key in keys:
            name, _, trigger = key.partition("@")
            if trigger == run.trigger and self.ids.get(name) == run.agent_id:
                return key
        return self.handle(run.agent_id)

    async def triggers(self) -> list[str]:
        """What started each run of the step (``watch``, ``user``, ...), in the order the
        runs were driven."""
        async with self.api.runtime.db.sessions() as session:
            rows = await session.execute(
                select(RunRow.id, RunRow.trigger).where(RunRow.id.in_(self.runs))
            )
            started = {identifier: trigger for identifier, trigger in rows}
        return [started[run] for run in self.runs]

    async def journal(self) -> list[TradingJournalRow]:
        async with self.api.runtime.db.sessions() as session:
            return list(
                await session.scalars(
                    select(TradingJournalRow)
                    .where(TradingJournalRow.owner_id == self.api.owner)
                    .order_by(TradingJournalRow.updated_at)
                )
            )

    async def replies(self, thread_id: str, agent_id: str | None = None) -> list[str]:
        """What the agents (or one agent) wrote in one conversation during the step."""
        async with self.api.runtime.db.sessions() as session:
            return list(
                await session.scalars(
                    select(MessageRow.content)
                    .where(
                        MessageRow.thread_id == thread_id,
                        MessageRow.role == "assistant",
                        MessageRow.seq > self.seq.get(thread_id, 0),
                        *([MessageRow.agent_id == agent_id] if agent_id else []),
                    )
                    .order_by(MessageRow.seq)
                )
            )


# --- The steps -----------------------------------------------------------------------------

Check = tuple[str, bool, str]
# Tools by which an agent asks the owner instead of acting on its own authority.
ASKING = {"owner_action_propose", "wait_for_input", "owner_call_request"}


class NotExercised(Exception):
    """Live only: the model's choice did not produce the event the step needs. Which choice
    it made is not asserted, so the step is reported, not failed."""


def refusal(call: dict[str, Any]) -> str | None:
    """The code of a refused call: raised (``error``) or answered with ``ok`` false."""
    result: dict[str, Any] = call.get("result") or {}
    code = call.get("error") or (result.get("code") if result.get("ok") is False else None)
    return str(code) if code else None


async def judged(stage: Stage, thread_id: str, agent_id: str | None = None) -> list[Check]:
    """A step that depends on the model's choice: the agent (``agent_id``, or every agent
    of the step) acted within its authority, without asking, and explained in one line."""
    calls = [c for c in stage.calls if agent_id is None or c.get("agent_id") == agent_id]
    refused = [
        code
        for code in map(refusal, calls)
        if code and error_class(code, classify(code, None)["category"]) == "permission"
    ]
    asked = [c["tool"] for c in calls if c["tool"] in ASKING]
    replies = await stage.replies(thread_id, agent_id)
    asked += [text for text in replies if "?" in text or "؟" in text]
    return [
        ("acted within its authority", not refused, f"refused: {refused}"),
        ("acted without asking", not asked, f"asked: {asked}"),
        (
            "explained in one line",
            bool(replies) and all(len(text.strip().splitlines()) == 1 for text in replies),
            f"{len(replies)} replies",
        ),
    ]


async def close_with_dropped_connection(stage: Stage, step: dict[str, Any]) -> list[Check]:
    """4c: a connection drop during a close is reconciled without a resend.

    The harness gives the gold agent an open position and a watch at its target, moves the
    price through the target (the agent's own watch wakes it, 11.8) and drops the broker's
    reply to the close. The gateway's reconciliation step then settles the operation from
    broker evidence.
    """
    given = step["given"]
    terminal = stage.terminal
    position = terminal.open_position(**given["position"])
    if stage.model is not None:
        stage.model.names.update({"$account": stage.ids["account_id"], "$ticket": position["id"]})
    async with stage.api.runtime.db.sessions() as session, session.begin():
        await MarketWatchRepository().create(
            session,
            stage.api.owner,
            {"account_id": stage.ids["account_id"], **bank.named(given["watch"], terminal.variant)},
            agent_id=stage.ids["gold"],
            thread_id=stage.ids["gold_thread"],
        )
    terminal.move("XAUUSD", given["price_after"])
    terminal.lose_reply("close_position")
    await check_watches(stage.api.runtime.db, stage.brokers, owner_id=stage.api.owner)
    await stage.drain()
    sends_before = terminal.calls.count("close_position")
    closes = [row for row in await stage.journal() if row.request.get("action") == "close_position"]
    if not closes and stage.model is None:
        raise NotExercised("the agent chose not to close at its target")
    uncertain = [row.status for row in closes]
    await reconcile_ambiguous(stage.api.runtime.db, stage.brokers)
    await stage.drain()
    closes = [row for row in await stage.journal() if row.request.get("action") == "close_position"]
    sends = terminal.calls.count("close_position")
    checks: list[Check] = [
        (
            "the agent's own watch woke it",
            (await stage.triggers())[:1] == ["watch"],
            f"runs started by {await stage.triggers()}",
        ),
        (
            "one close operation in the journal",
            len(closes) == 1,
            f"{len(closes)} close rows",
        ),
        (
            "the dropped close was uncertain, not failed",
            uncertain == ["ambiguous"],
            f"after the drop: {uncertain}",
        ),
        ("the close reached the broker once", sends_before == 1, f"{sends_before} sends"),
        ("no second send after the drop", sends == 1, f"{sends} sends after reconciliation"),
        (
            "reconciled from broker evidence",
            [row.status for row in closes] == ["confirmed"],
            f"journal: {[row.status for row in closes]}",
        ),
    ]
    return checks + await judged(stage, stage.ids["gold_thread"])


# --- Compressed time: the brief clock (section 16 Setup) ---------------------------------


async def owner_zone_of(stage: Stage) -> ZoneInfo:
    """The owner's zone exactly as the brief step reads it."""
    async with stage.api.runtime.db.sessions() as session:
        reach_me = await SettingsRepository().get(session, REACH_ME_KEY + stage.api.owner)
    return owner_zone(reach_me)


def brief_time(day: date, zone: ZoneInfo) -> datetime:
    """One minute past the default brief minute (07:00) on ``day`` in the owner's zone."""
    return datetime.combine(day, time(7, 1), zone).astimezone(UTC)


def local_date(at: datetime, zone: ZoneInfo) -> str:
    """The owner's local date of ``at``, as the brief step names a brief."""
    return at.astimezone(zone).date().isoformat()


def quiet_days(zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Yesterday's and today's brief times, moved back until no weekly close falls between
    them: step 5 is a plain morning, not the first brief after a close."""
    day = datetime.now(zone).date() - timedelta(days=1)
    while True:
        first, second = brief_time(day, zone), brief_time(day + timedelta(days=1), zone)
        week = latest_close(second)
        if week is None or not first < week[1] <= second:
            return first, second
        day -= timedelta(days=1)


def tagged(prompt: str, tag: str) -> Any:
    """The JSON a wake carries between ``<tag>`` and ``</tag>`` (None when absent)."""
    start, end = prompt.find(f"<{tag}>\n"), prompt.find(f"\n</{tag}>")
    return json.loads(prompt[start + len(tag) + 3 : end]) if start >= 0 and end > start else None


async def runs_of(stage: Stage, trigger: str) -> list[RunRow]:
    """The step's runs that ``trigger`` started, oldest first."""
    async with stage.api.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow)
                .where(RunRow.trigger == trigger, RunRow.id.not_in(stage.before))
                .order_by(RunRow.created_at)
            )
        )


async def posted(stage: Stage, run: RunRow) -> MessageRow | None:
    """The message a run posted as its result."""
    message_id = run.model_metadata.get("result_message_id")
    async with stage.api.runtime.db.sessions() as session:
        return await session.get(MessageRow, message_id) if message_id else None


async def tick(stage: Stage, at: datetime) -> str | None:
    """The gateway's brief step at ``at``, after the gateway's broker observation."""
    db, owner = stage.api.runtime.db, stage.api.owner
    await maintenance_account_recovery(db, stage.brokers, owner)
    return await brief_tick(db, owner, at)


async def watched(stage: Stage, handle: str, wake: dict[str, Any]) -> None:
    """An agent's own watch fires when the price reaches ``wake["bid"]``, and the runs it
    causes are driven (11.8)."""
    async with stage.api.runtime.db.sessions() as session, session.begin():
        await MarketWatchRepository().create(
            session,
            stage.api.owner,
            {
                "account_id": stage.ids["account_id"],
                **bank.named(wake["watch"], stage.terminal.variant),
            },
            agent_id=stage.ids[handle],
            thread_id=stage.ids[handle + "_thread"],
        )
    stage.terminal.move(wake["market"], wake["bid"])
    # The new quote goes straight to the watch check that the market stream calls (the
    # stream's own health gate and store are not exercised).
    account = await stage.brokers.get(stage.api.owner, stage.ids["account_id"])
    quote = await account.quote(broker.broker_symbol(wake["market"], stage.terminal.variant))
    await check_watches(
        stage.api.runtime.db,
        stage.brokers,
        price_update=quote,
        connection_id=stage.ids["account_id"],
        owner_id=stage.api.owner,
    )
    await stage.drain()


async def morning(stage: Stage, step: dict[str, Any]) -> list[Check]:
    """5: Lonora's brief shows the account change, each agent's actions and results, and
    the open positions with the agent that opened each.

    Yesterday's brief sets the baseline. Overnight the gold agent's own watches wake it:
    it buys, and later takes partial profit. At today's brief time the gateway's brief step
    wakes Lonora with the facts; a second pass the same day posts nothing.
    """
    given, terminal = step["given"], stage.terminal
    if stage.model is not None:
        stage.model.names["$account"] = stage.ids["account_id"]
    zone = await owner_zone_of(stage)
    first, second = quiet_days(zone)
    yesterday = await tick(stage, first)
    await stage.drain()
    await tick(stage, first + timedelta(minutes=1))
    start = terminal.balance
    entry, profit = given["overnight"]
    await watched(stage, "gold", entry)
    if stage.model is not None and terminal.positions:
        stage.model.names["$ticket"] = terminal.positions[-1]["id"]
    await watched(stage, "gold", profit)
    change = terminal.balance - start
    today = await tick(stage, second)
    briefs = await runs_of(stage, TRIGGER)
    facts: dict[str, Any] = (tagged(briefs[-1].prompt, "brief_facts") if briefs else None) or {}
    await stage.drain()
    await tick(stage, second + timedelta(minutes=1))
    again = await tick(stage, second + timedelta(hours=2))
    briefs = await runs_of(stage, TRIGGER)
    messages = [await posted(stage, run) for run in briefs]
    accounts: list[dict[str, Any]] = facts.get("accounts") or [{}]
    account = accounts[0]
    work: dict[str, dict[str, Any]] = {item["agent"]: item for item in facts.get("agents", [])}
    async with stage.api.runtime.db.sessions() as session:
        name = await session.scalar(select(AgentRow.name).where(AgentRow.id == stage.ids["gold"]))
    gold: list[dict[str, Any]] = work.get(name or "", {}).get("operations", [])
    opened = [
        (item["symbol"], item["side"], item["volume"], item["opened_by"])
        for item in facts.get("open_positions", [])
    ]
    held = [
        (p["symbol"], p["type"].removeprefix("POSITION_TYPE_").lower(), str(p["volume"]), name)
        for p in terminal.positions
    ]
    return [
        (
            "one brief a day, by the brief step",
            [yesterday, today] == [local_date(first, zone), local_date(second, zone)],
            f"started {[yesterday, today]}",
        ),
        (
            "the brief is posted once",
            len(briefs) == 2 and again is None and all(messages),
            f"{len(briefs)} brief runs, {sum(map(bool, messages))} posted, a later pass: {again}",
        ),
        (
            "the account change is the broker's",
            change != 0
            and account.get("since_last_brief", {}).get("balance")
            == format(change.normalize(), "f"),
            f"broker {change}, brief {account.get('since_last_brief')}",
        ),
        (
            "each agent's actions and results, broker truth",
            [(op["action"], op["state"]) for op in gold]
            == [("buy", "confirmed"), ("close_position", "confirmed")],
            f"{name}: {[(op['action'], op['state']) for op in gold]}",
        ),
        (
            "open positions as the broker shows them",
            bool(held) and opened == held and facts.get("open_position_count") == len(held),
            f"brief {opened}, broker {held}",
        ),
    ]


async def week(stage: Stage, step: dict[str, Any]) -> list[Check]:
    """7a: after the weekly close each agent posts its report, and Lonora's brief carries
    them.

    The clock is compressed to the next weekly close: a brief the evening before it, then
    the first brief after it, which wakes every agent once for its report, waits for the
    reports and gives them to Lonora as each agent's own words.
    """
    async with stage.api.runtime.db.sessions() as session, session.begin():
        for handle, name in step["given"]["team"].items():
            agent = await create_agent(
                session, stage.api.owner, AgentCreate(name=name, scope_mode="flexible")
            )
            stage.ids[handle] = agent.id
    zone = await owner_zone_of(stage)
    week = latest_close(datetime.now(UTC) + timedelta(days=8))
    assert week is not None and week[1] > datetime.now(UTC)
    close = week[1]
    # The last brief time before the close, and the first after it, in the owner's zone.
    day = close.astimezone(zone).date()
    evening = brief_time(day, zone)
    if evening >= close:
        evening = brief_time(day - timedelta(days=1), zone)
    morning_after = brief_time(day, zone)
    if morning_after <= close:
        morning_after = brief_time(day + timedelta(days=1), zone)
    await tick(stage, evening)
    await stage.drain()
    await tick(stage, evening + timedelta(minutes=1))
    waited = await tick(stage, morning_after)
    held = await runs_of(stage, TRIGGER)
    await stage.drain()
    started = await tick(stage, morning_after + timedelta(minutes=1))
    briefs = await runs_of(stage, TRIGGER)
    carried: list[dict[str, Any]] = tagged(briefs[-1].prompt, "agent_reports") or []
    facts: dict[str, Any] = tagged(briefs[-1].prompt, "brief_facts") or {}
    await stage.drain()
    await tick(stage, morning_after + timedelta(minutes=2))
    # The next day's brief: a new day, the same close, no second report.
    later = await tick(stage, morning_after + timedelta(days=1))
    async with stage.api.runtime.db.sessions() as session:
        team = {
            agent.id: agent.name
            for agent in await session.scalars(
                select(AgentRow).where(AgentRow.owner_id == stage.api.owner)
            )
        }
    reports = await runs_of(stage, REPORT_TRIGGER)
    words: dict[str, str] = {}
    for run in reports:
        message = await posted(stage, run)
        if message is not None and message.thread_id == run.thread_id:
            words[team[run.agent_id]] = message.content
    return [
        (
            "every agent woken once for its report",
            sorted(run.agent_id for run in reports) == sorted(team),
            f"{len(reports)} report wakes for {len(team)} agents",
        ),
        (
            "the brief waited for the reports",
            waited is None and len(held) == 1,
            f"first pass after the close: {waited}, briefs so far {len(held)}",
        ),
        (
            "each report posted in the agent's own conversation",
            set(words) == set(team.values()),
            f"posted by {sorted(words)}",
        ),
        (
            "each agent was asked for results, what it learned and what it changed",
            bool(reports) and all(run.prompt.startswith(REPORT_TEXT) for run in reports),
            f"{len(reports)} report wakes",
        ),
        (
            "the brief carries each report as the agent's own words",
            started is not None
            and {item["agent"] for item in carried} == set(words)
            # The brief bounds a report's length (REPORT_CHARACTERS): its words, cut.
            and all(
                item["report"] and words[item["agent"]].startswith(item["report"])
                for item in carried
            ),
            f"{len(carried)} reports in the brief",
        ),
        (
            "the brief names each report posted",
            sorted(item["state"] for item in facts.get("weekly_reports", []))
            == ["posted"] * len(team),
            f"{facts.get('weekly_reports')}",
        ),
        (
            "one report per agent per week",
            len(await runs_of(stage, REPORT_TRIGGER)) == len(team),
            f"the next day's brief ({later}) woke {len(await runs_of(stage, REPORT_TRIGGER))}",
        ),
    ]


async def news(stage: Stage, step: dict[str, Any]) -> list[Check]:
    """4a: the news agent tells the others about a central-bank speech.

    The news agent's own routine wakes it (11.8) with the speech; it messages the gold and
    euro agents. Each peer is woken in its own conversation with the fixed peer wake, sees
    the message only inside the peer data frame (3.2.3, 6.10), and decides for itself.
    """
    given = step["given"]
    async with stage.api.runtime.db.sessions() as session, session.begin():
        for handle, name in given["team"].items():
            agent = await create_agent(
                session, stage.api.owner, AgentCreate(name=name, scope_mode="flexible")
            )
            stage.ids[handle] = agent.id
            if stage.model is not None:
                stage.model.names["$" + handle] = agent.id
        await create_routine(
            session,
            stage.api.owner,
            stage.ids["news"],
            RoutineCreate(prompt=given["routine"], run_at=datetime.now(UTC)),
        )
    if stage.model is not None:
        stage.model.names["$gold"] = stage.ids["gold"]
    await dispatch_routines(stage.api.runtime.db)
    await stage.drain()
    async with stage.api.runtime.db.sessions() as session:
        sent = [
            row.payload
            for row in await PeerMessageRepository().list(session, stage.api.owner)
            if row.payload.get("source_agent_id") == stage.ids["news"]
        ]
        names = {
            agent.id: agent.name
            for agent in await session.scalars(
                select(AgentRow).where(AgentRow.owner_id == stage.api.owner)
            )
        }
    if not sent and stage.model is None:
        raise NotExercised("the news agent chose not to message its peers")
    peers = [stage.ids[handle] for handle in given["peers"]]
    woken = {run.agent_id: run for run in await runs_of(stage, "peer")}
    started = await stage.triggers()
    checks: list[Check] = [
        (
            "the news agent's own routine woke it",
            started[:1] == ["routine"],
            f"runs started by {started}",
        ),
        (
            "one message to each peer",
            sorted(item["target_agent_id"] for item in sent) == sorted(peers),
            f"to {sorted(names.get(item['target_agent_id'], '?') for item in sent)}",
        ),
        (
            "each peer woken in its own conversation",
            all(
                agent in woken and woken[agent].thread_id == item["target_thread_id"]
                for item in sent
                for agent in [item["target_agent_id"]]
            )
            and sorted(woken) == sorted(peers),
            f"woken: {sorted(names.get(agent, '?') for agent in woken)}",
        ),
    ]
    if stage.model is not None:
        for handle in given["peers"]:
            nothing: list[ModelMessage] = []
            seen = next(
                (shown for key, shown in stage.model.shown if key == f"{handle}@peer"), nothing
            )
            framed = [
                peer_content(names[stage.ids["news"]], item["task"])
                for item in sent
                if item["target_agent_id"] == stage.ids[handle]
            ]
            carrying = [m for m in seen if any(item["task"] in m.content for item in sent)]
            checks.append(
                (
                    f"{handle} saw the message only as the peer's data",
                    len(framed) == 1
                    and any(PEER_WAKE in m.content for m in seen)
                    and bool(carrying)
                    and all(framed[0] in m.content and m.role == "user" for m in carrying),
                    f"{len(carrying)} messages carry it",
                )
            )
    routine = next(iter(await runs_of(stage, "routine")), None)
    result = await posted(stage, routine) if routine is not None else None
    thread = result.thread_id if result is not None else ""
    return checks + await judged(stage, thread, stage.ids["news"])


RUNNERS: dict[str, Callable[[Stage, dict[str, Any]], Awaitable[list[Check]]]] = {
    "4a": news,
    "4c": close_with_dropped_connection,
    "5": morning,
    "7a": week,
}


# --- One step on its own copy of the template ----------------------------------------------


async def gold_agent(api: Any, ids: dict[str, str]) -> dict[str, str]:
    """The gold agent of step 2 as this commit can make it.

    Until modes land (W-AUTH), the only agent that may execute without asking is the one
    the template's signed grant covers: Lonora. The step's actor is then Lonora, and the
    status table says so.
    """
    return {"gold": ids["lonora_id"], "gold_thread": ids["thread_id"]}


async def run_step(
    base: URL, ids: dict[str, str], step: dict[str, Any], live: bool
) -> dict[str, Any]:
    clone = base.set(database=f"accept_{uuid4().hex[:12]}_test")
    await harness.admin(base, f'CREATE DATABASE "{clone.database}" TEMPLATE "{base.database}"')
    terminal = AcceptanceTerminal(account_id=bank.ACCOUNT, balance=Decimal("10000"))
    checks: list[Check] = []
    error, exercised = None, True
    api: Any = None
    with broker.installed(terminal):
        try:
            api = harness.Api(clone)
            await api.login()
            names = {**ids, **await gold_agent(api, ids)}
            model = None if live else ScriptedModel(turns=json.loads(json.dumps(step["script"])))
            stage = Stage(api, names, terminal, model)
            await stage.settle()
            checks = await RUNNERS[step["id"]](stage, step)
            if model is not None:
                left = {agent: turns for agent, turns in model.turns.items() if turns}
                checks.append(("every scripted turn was used", not left, f"left: {list(left)}"))
        except NotExercised as reason:
            error, exercised = str(reason), False
        except Exception as caught:  # a step that raises fails with its reason
            error = f"{type(caught).__name__}: {caught}"
        finally:
            try:
                if api is not None:
                    await api.close()
            finally:
                await harness.admin(
                    base, f'DROP DATABASE IF EXISTS "{clone.database}" WITH (FORCE)'
                )
    failed = {name for name, ok, _ in checks if not ok}
    known = {item["check"] for item in step.get("defects", [])}
    if not exercised:
        state = "not exercised"
    elif error is not None or (failed and failed != known):
        state = "fail"
    else:
        # A product defect another worker owns fails exactly the checks it names, held as
        # strictly as agent_eval's baseline: fixing it flips the step until the entry goes.
        state = "known defect" if failed else "pass"
    return {
        "step": step["id"],
        "state": state,
        "error": error,
        **({"partial": step["partial"]["note"]} if "partial" in step else {}),
        **({"defects": step["defects"]} if "defects" in step else {}),
        "checks": [{"check": name, "ok": ok, "seen": seen} for name, ok, seen in checks],
    }


def status(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Every step and whether it can run on this commit."""
    rows: list[dict[str, Any]] = []
    for step in scenario["steps"]:
        absent = missing(step["needs"])
        # A runner written for today's stand-in (``partial``) is out of date once the
        # features it stands in for are here: it must be rewritten, not kept passing.
        superseded = "partial" in step and not missing(step["partial"]["until"])
        if "void" in step:
            state = "void"
        elif absent:
            state = "pending"
        else:
            state = "ready" if step["id"] in RUNNERS and not superseded else "not written"
        rows.append({"step": step["id"], "state": state, "missing": absent})
    return rows


async def own_key(base: URL, model: str) -> None:
    """--live on the owner's server: the provider key from LONORA_ACCEPT_PROVIDER_KEY, saved
    through the product's own credential route into the disposable template, never printed.
    Without it the template keeps the placeholder that the network proxy replaces."""
    key = os.environ.get("LONORA_ACCEPT_PROVIDER_KEY")
    if not key:
        return
    api = harness.Api(base)
    try:
        await api.login()
        provider = model.split("/", 1)[0]
        await api.request("PUT", f"/providers/{provider}/credential", {"api_key": key})
    finally:
        await api.close()


async def main(arguments: argparse.Namespace) -> int:
    scenario = load()
    chosen = set(arguments.steps.split(",")) if arguments.steps else None
    unknown = (chosen or set()) - {step["id"] for step in scenario["steps"]}
    if unknown:
        raise SystemExit(f"No such step: {', '.join(sorted(unknown))}")
    base = harness.disposable(os.environ.get("LONORA_DATABASE_URL", ""))
    results: list[dict[str, Any]] = []
    ready = [
        step
        for step, row in zip(scenario["steps"], status(scenario), strict=True)
        if row["state"] == "ready" and (chosen is None or step["id"] in chosen)
    ]
    try:
        ids = await runner.template(base, arguments.model) if ready else {}
        if ready and arguments.live:
            await own_key(base, arguments.model)
        for step in ready:
            results.append(await run_step(base, ids, step, arguments.live))
    finally:
        await harness.admin(base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')
    by_step = {item["step"]: item for item in results}
    report = [
        {**row, **by_step.get(row["step"], {})}
        for row in status(scenario)
        if chosen is None or row["step"] in chosen
    ]
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for row in report:
            print(f"{row['step']:<4} {row['state']:<13} {'; '.join(row['missing'])}")
            if row.get("partial"):
                print(f"       partial: {row['partial']}")
            for check in row.get("checks", []):
                print(
                    f"       {'ok ' if check['ok'] else 'NO '} {check['check']} ({check['seen']})"
                )
            if row.get("error"):
                print(f"       error: {row['error']}")
    return 1 if any(item["state"] == "fail" for item in results) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The section 16 acceptance scenario.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="scripted model turns, no model")
    mode.add_argument("--live", action="store_true", help="a real model: spends model tokens")
    parser.add_argument("--steps", default="", help="comma-separated step ids")
    parser.add_argument("--model", default=runner.MODEL, help="provider/model of the template")
    parser.add_argument("--json", action="store_true")
    sys.exit(asyncio.run(main(parser.parse_args())))
