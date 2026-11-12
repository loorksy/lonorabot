"""Simple Lonora acceptance (W15-ACC) on a fresh migrated PostgreSQL database.

The owner's journeys of the previous vision run end to end through the normal entry points:
Arabic owner messages go to the chat API (``POST /threads/{id}/messages``), each Run is
claimed and executed by the gateway's agent runtime, the model is a scripted provider
behind the real model router (``OwnerServices.router``), market and order state come from
the simulation broker, and every owner decision is a request to the owner routes a Web or
Mobile card sends (with a scripted passkey where the card needs one).

For each journey it counts the owner's confirmations and checks them against that vision,
and across all of them it checks four properties:

1. Nothing trades without a grant or a tap: the broker's book changes only after the
   owner signed a grant or tapped an approval.
2. A worker restart in the middle of a Run never adds a second operation, watch, agent or
   card: the restarted worker continues the same Run and a model that repeats itself is
   answered with what already exists.
3. The status line, the cards and the durable records agree.
4. No credential value appears in a message, an event, a card, a Run or anything the
   model was sent.

No live broker, model provider, MetaApi account or real device is involved.
"""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.events import emit
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import run_data
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    AttentionRow,
    EventRow,
    MarketWatchRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    SupervisionGrantRow,
    TradeApprovalRow,
    TradingAccountRow,
    TradingJournalRow,
    TradingRestrictionRow,
    TrustedSourceRow,
)
from lonora_gateway.attention import attention_tick
from lonora_gateway.run_dispatch import run_model_choice
from lonora_gateway.service import Gateway
from lonora_tools import mcp
from lonora_trading.broker_recovery import reconcile_broker_account
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import func, select

GOLD, SILVER, EURO = "XAUUSD", "XAGUSD", "EURUSD"
PROVIDER_KEY = "acc-provider-key-" + uuid4().hex
MCP_TOKEN = "acc-mcp-token-" + uuid4().hex
MCP_URL = "https://x-mcp.example.test/" + uuid4().hex[:8]
NOTES_URL = "https://notes-mcp.example.test/" + uuid4().hex[:8]
DONE = "تم."
# Every credential value the check hands to the server; none may leave it.
SECRETS = (PROVIDER_KEY, MCP_TOKEN)


# --- The scripted provider ---------------------------------------------------------------


@dataclass
class Turn:
    """What the model sees of the current trigger: its tool results so far."""

    messages: list[ModelMessage]
    offered: list[str]
    step: int

    def result(self, call_id: str) -> dict[str, Any]:
        for message in reversed(self.messages):
            if message.role == "tool" and message.tool_call_id == call_id:
                return cast(dict[str, Any], json.loads(message.content))
        raise AssertionError("no result for " + call_id)


Step = Callable[[Turn], "ModelReply | Awaitable[ModelReply]"] | str


@dataclass
class Script:
    """One owner request (or wake) the scripted model answers, step by step.

    The step is the number of model turns since the trigger, read from the transcript
    the runtime sends, so a restarted worker that continues the Run continues the script.
    """

    key: str
    steps: list[Step]
    attempts: dict[int, int] = field(default_factory=dict[int, int])

    async def reply(self, turn: Turn) -> ModelReply:
        self.attempts[turn.step] = self.attempts.get(turn.step, 0) + 1
        step = self.steps[min(turn.step, len(self.steps) - 1)]
        if isinstance(step, str):
            return ModelReply(text=step)
        value = step(turn)
        return await value if isinstance(value, Awaitable) else value


class ScriptedProvider:
    """A model provider adapter answered by scripts; it records everything it was sent."""

    def __init__(self) -> None:
        self.scripts: list[Script] = []
        self.sent: list[list[ModelMessage]] = []
        self.offered: list[list[str]] = []
        self.unscripted: list[str] = []

    def script(self, key: str, *steps: Step) -> Script:
        script = Script(key, list(steps))
        self.scripts.append(script)
        return script

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply:
        self.sent.append(list(messages))
        names = [tool.name for tool in tools]
        self.offered.append(names)
        # The trigger: the newest user message a script answers (the owner's words, a
        # wake or a Task's brief; runtime notices that follow it keep the same script).
        users = [index for index, message in enumerate(messages) if message.role == "user"]
        matched = next(
            (
                (index, script)
                for index in reversed(users)
                for script in reversed(self.scripts)
                if script.key in messages[index].content
            ),
            None,
        )
        if matched is None:
            self.unscripted.append(messages[users[-1]].content[:160])
            reply = ModelReply(text=DONE)
        else:
            index, script = matched
            step = sum(1 for message in messages[index + 1 :] if message.role == "assistant")
            reply = await script.reply(Turn(messages, names, step))
        # A capability outside the Run's native tools is reached through tool_call, as a
        # real model does; the runtime unwraps it into the same call.
        reply = ModelReply(
            text=reply.text,
            tool_calls=[
                call
                if call.name in names
                else ToolCall(
                    id=call.id,
                    name="tool_call",
                    arguments={"name": call.name, "arguments": call.arguments},
                )
                for call in reply.tool_calls
            ],
        )
        if on_delta and reply.text:
            await on_delta(reply.text)
        return reply

    async def discover(self) -> list[Any]:
        return []

    async def close(self) -> None:
        return None


def call(call_id: str, name: str, arguments: dict[str, Any]) -> ModelReply:
    return ModelReply(tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])


def calls(*items: tuple[str, str, dict[str, Any]]) -> ModelReply:
    return ModelReply(tool_calls=[ToolCall(id=i, name=n, arguments=a) for i, n, a in items])


def crash_then(reached: asyncio.Event, then: Callable[[Turn], ModelReply]) -> Step:
    """The first time: the worker dies while the model is thinking (it is cancelled while
    it waits, as a stopped process never answers). Afterwards: ``then``."""
    seen = {"count": 0}

    async def step(turn: Turn) -> ModelReply:
        seen["count"] += 1
        if seen["count"] == 1:
            reached.set()
            await asyncio.Event().wait()
        return then(turn)

    return step


def next_london_close() -> str:
    """Today's London session close (17:00 London), or tomorrow's once it has passed."""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    london = ZoneInfo("Europe/London")
    now = datetime.now(london)
    close = datetime.combine(now.date(), time(17, 0), london)
    if close <= now:
        close = datetime.combine(now.date() + timedelta(days=1), time(17, 0), london)
    return close.isoformat()


# --- Broker fixtures ---------------------------------------------------------------------


def quote(symbol: str, bid: str, ask: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "observed_at": utcnow().isoformat(),
        "source": "explicit-simple-lonora-fixture",
        "loss_tick_value": "1",
        "profit_tick_value": "1",
        "tick_value_basis": "account_currency_per_lot",
    }


PRICES = {GOLD: ("2000.00", "2000.50"), SILVER: ("24.00", "24.05"), EURO: ("1.1000", "1.1002")}


def snapshot() -> dict[str, Any]:
    return {
        "currency": "USD",
        "balance": "10000",
        "equity": "10000",
        "instruments": [
            {
                "symbol": symbol,
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.01",
                "volume_max": "10",
                "volume_step": "0.01",
            }
            for symbol in PRICES
        ],
        "quotes": {symbol: quote(symbol, *prices) for symbol, prices in PRICES.items()},
    }


class CrashAfterSend(SimulationBroker):
    """The broker applies the order, then the worker process dies before the reply."""

    reached: asyncio.Event

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        await super().execute(request, before_send)
        self.reached.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class LostAcknowledgement(SimulationBroker):
    """The broker applies the order but its acknowledgement never arrives."""

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        await super().execute(request, before_send)
        raise TimeoutError("explicit acknowledgement loss after the simulated effect")


# --- MCP fixture (D3: X through a trusted MCP server) -----------------------------------

SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


def x_server(calls_seen: list[str], tokens: list[str | None]) -> Any:
    """A scripted MCP server (X analysts' posts, and the notes server of J6): one read-only
    search tool and one tool that could place orders, which is never trusted."""

    def create(url: str, token: str | None = None) -> Any:
        assert url in {MCP_URL, NOTES_URL}, url
        tokens.append(token)

        class Transport:
            async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
                method = payload["method"]
                calls_seen.append(method)
                if method == "notifications/initialized":
                    return {}
                if method == "initialize":
                    result: dict[str, Any] = {"protocolVersion": "2025-06-18"}
                elif method == "tools/list":
                    result = {
                        "tools": [
                            {
                                "name": "search_posts",
                                "description": "Search public posts by analysts.",
                                "inputSchema": SEARCH_SCHEMA,
                                "annotations": {"readOnlyHint": True},
                            },
                            {"name": "place_order", "inputSchema": SEARCH_SCHEMA},
                        ]
                    }
                else:
                    result = {"content": [{"type": "text", "text": "Analyst: gold bid into CPI"}]}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

            async def close(self) -> None:
                pass

        return Transport()

    return create


SKILL = (
    "---\nname: cpi-brief\ndescription: Summarize CPI releases and their effect on gold.\n"
    "---\nUse only cited evidence. This procedure never authorizes financial actions.\n"
)
SKILL_REVIEW = {
    "source_behavior": "Summarize a CPI release from cited sources.",
    "adapted_behavior": "Summarize CPI releases for the owner in Arabic, citing sources.",
    "assumptions": ["The release and its sources are supplied and cited."],
    "limitations": ["It summarizes; it does not predict prices."],
}


def skill_archive() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as bundle:
        bundle.writestr("root/cpi-brief/SKILL.md", SKILL)
    return output.getvalue()


# --- The acceptance run ------------------------------------------------------------------


class Acceptance:
    def __init__(self, fixture: Fixture) -> None:
        self.fixture = fixture
        self.db = fixture.runtime.db
        self.owner = fixture.owner
        self.services = fixture.runtime.services(fixture.owner)
        self.model = ScriptedProvider()
        model = self.model

        def factory(provider: str, key: str) -> Any:
            return model

        self.services.router.factory = factory
        self.gateway = Gateway(
            self.db,
            fixture.settings.encryption_key.get_secret_value(),
            fixture.settings.artifact_root,
        )
        self.gateway.services[fixture.owner] = self.services
        self.confirmations: dict[str, int] = {}
        self.results: list[tuple[str, int, int]] = []
        self.account = ""
        self.second_account = ""
        self.lonora = ""
        self.lonora_thread = ""
        self.device: Device | None = None
        self.created: list[str] = []
        self.set_aside: list[str] = []
        self.watch_name = ""

    # Owner-side requests -----------------------------------------------------------

    async def request(self, method: str, path: str, body: Any = None) -> Any:
        response = await self.fixture.client.request(method, "/api" + path, json=body)
        assert response.is_success, f"{method} {path}: {response.status_code} {response.text}"
        return response.json()

    async def raw(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        response = await self.fixture.client.request(method, "/api" + path, json=body)
        return response.status_code, response.json()

    def tap(self, journey: str) -> None:
        """One owner confirmation: a tap on a card or approval, or a passkey."""
        self.confirmations[journey] = self.confirmations.get(journey, 0) + 1

    def journey(self, name: str, expected: int, note: str = "") -> None:
        """``expected`` is the count by the vision's rule of when Lonora asks; ``note``
        says where that differs from the slice's journey list."""
        taken = self.confirmations.get(name, 0)
        assert taken == expected, (name, taken, expected)
        self.results.append((name, taken, expected))
        print(
            f"PASS {name}: {taken} owner confirmation(s), as expected ({expected})"
            + (f"; {note}" if note else "")
        )

    async def cards(self, thread_id: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], await self.request("GET", f"/owner-actions?thread_id={thread_id}")
        )

    async def pending(self, thread_id: str, kind: str) -> list[dict[str, Any]]:
        return [
            card
            for card in await self.cards(thread_id)
            if card["kind"] == kind and card["status"] == "pending"
        ]

    async def decide(self, journey: str, card_id: str, body: dict[str, Any]) -> dict[str, Any]:
        decided = await self.request("POST", f"/owner-actions/{card_id}/decision", body)
        if body.get("decision") == "confirm":
            self.tap(journey)
        return cast(dict[str, Any], decided)

    async def passkey(self, journey: str, card_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Authorize on the card: the first time on this device it enrolls it inline."""
        if self.device is None:
            self.device = await Device.enroll(self.fixture)
        challenge = await self.request("POST", f"/owner-actions/{card_id}/challenge", {})
        proof = self.device.assertion(challenge, self.fixture.settings.allowed_origin)
        return await self.decide(journey, card_id, {"decision": "confirm", "proof": proof, **body})

    async def say(self, thread_id: str, words: str) -> str:
        sent = await self.request(
            "POST",
            f"/threads/{thread_id}/messages",
            {"content": words, "client_nonce": "acc-" + uuid4().hex},
        )
        return cast(str, sent["run_ids"][0])

    async def lines(self, thread_id: str) -> list[str]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(MessageRow.content)
                    .where(MessageRow.thread_id == thread_id, MessageRow.role == "assistant")
                    .order_by(MessageRow.seq)
                )
            )

    async def conversation(self, agent_id: str) -> str:
        return cast(str, (await self.request("POST", f"/agents/{agent_id}/conversation", {}))["id"])

    async def state(self, agent_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], await self.request("GET", f"/agents/{agent_id}/state"))

    async def level(self, agent_id: str) -> str:
        state = await self.request("GET", f"/agents/{agent_id}/permissions")
        return cast(str, state["effective_level"])

    async def project(self) -> None:
        """The gateway's attention step: cards raised from events, with no model."""
        for _ in range(4):
            await attention_tick(self.db, self.services.brokers, self.owner)

    async def refresh_quotes(self, account: str) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account, with_for_update=True)
            assert row is not None
            row.payload = {
                **row.payload,
                "quotes": {symbol: quote(symbol, *prices) for symbol, prices in PRICES.items()},
            }

    async def positions(self, account: str) -> list[dict[str, Any]]:
        async with self.db.sessions() as session:
            row = await session.get(TradingAccountRow, account, populate_existing=True)
            assert row is not None
            return list(row.payload.get("positions", []))

    # The worker ---------------------------------------------------------------------

    async def work(self, run_id: str, worker: str = "acc-worker") -> RunRow:
        """Claim this Run as the gateway's claim does and execute it in its runtime.

        A Run still ``running`` under an expired lease is a recovery: the fence moves on,
        so the dead worker can never write again, and the runtime continues from the
        Run's checkpoint.
        """
        now = utcnow()
        async with self.db.sessions() as session, session.begin():
            row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
            assert row is not None
            assert row.status == "queued" or (
                row.status in {"leased", "running"}
                and row.lease_expires_at is not None
                and row.lease_expires_at <= now
            ), (row.status, row.lease_expires_at)
            recovered = row.status != "queued"
            row.recovery_count = row.recovery_count + 1 if recovered else 0
            row.status, row.lease_owner = "leased", worker
            row.lease_fence += 1
            row.lease_expires_at = now + timedelta(seconds=120)
            row.updated_at, row.error_code = now, None
            emit(
                session,
                self.owner,
                "run.recovered" if recovered else "run.leased",
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                run_id=row.id,
                payload={"fence": row.lease_fence, "run": run_data(row)},
            )
            lease = Lease(run_id=row.id, owner=worker, fence=row.lease_fence)
            agent_id, thread_id = row.agent_id, row.thread_id
            depth = int(row.model_metadata.get("depth", 0))
            run_model = run_model_choice(row.model_metadata.get("model"))
        context = self.services.tool_context(
            agent_id,
            thread_id,
            lease,
            self.fixture.settings.artifact_root,
            depth,
            4,
            run_model,
        )
        await self.gateway.runtime.execute(context)
        async with self.db.sessions() as session:
            done = await session.get(RunRow, run_id, populate_existing=True)
            assert done is not None
            return done

    async def crash_and_restart(self, run_id: str, reached: asyncio.Event) -> RunRow:
        """Kill the worker while the Run is mid-flight; another worker takes it over."""
        worker = asyncio.create_task(self.work(run_id, "acc-worker-dying"))
        waiter = asyncio.create_task(reached.wait())
        done, _ = await asyncio.wait({worker, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if worker in done:
            waiter.cancel()
            raise AssertionError(
                ("the run ended before the crash", worker.result().status, self.model.unscripted)
            )
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        async with self.db.sessions() as session, session.begin():
            row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
            assert row is not None and row.status in {"leased", "running"}, row and row.status
            # The dead worker's lease runs out; nothing else changed.
            row.lease_expires_at = utcnow() - timedelta(seconds=1)
        return await self.work(run_id, "acc-worker-restarted")

    async def runs(self, agent_id: str, trigger: str | None = None) -> list[RunRow]:
        async with self.db.sessions() as session:
            query = select(RunRow).where(RunRow.agent_id == agent_id).order_by(RunRow.created_at)
            if trigger:
                query = query.where(RunRow.trigger == trigger)
            return list(await session.scalars(query))

    async def count(self, model: Any, *conditions: Any) -> int:
        async with self.db.sessions() as session:
            return int(
                await session.scalar(select(func.count()).select_from(model).where(*conditions))
                or 0
            )

    # Setup -----------------------------------------------------------------------------

    async def provider(self) -> None:
        """The owner's model settings, pointing at the scripted provider."""
        await self.request("PUT", "/providers/openai/credential", {"api_key": PROVIDER_KEY})
        await self.request(
            "PUT",
            "/settings/models",
            {
                "mode": "unified",
                "unified": {"provider": "openai", "model": "scripted-simple-lonora"},
                "routes": {},
            },
        )

    async def setup(self) -> None:
        await self.provider()
        # A shared database may hold other checks' agents: set them aside so the per-owner
        # limits count only this check's agents; restored at the end.
        async with self.db.sessions() as session, session.begin():
            for row in await session.scalars(
                select(AgentRow).where(
                    AgentRow.owner_id == self.owner,
                    AgentRow.role.not_in(["personal", "delegated"]),
                    AgentRow.paused.is_(False),
                )
            ):
                row.paused = True
                self.set_aside.append(row.id)
            self.lonora = (await ensure_personal_agent(session, self.owner)).id
        connection = await self.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "acc-" + uuid4().hex, "enabled": True},
        )
        self.account = connection["id"]
        await self.request(
            "POST", f"/trading/connections/{self.account}/simulation", {"snapshot": snapshot()}
        )
        await self.services.brokers.get(self.owner, self.account)
        self.lonora_thread = await self.conversation(self.lonora)
        print("PASS setup: one simulation account, Lonora, scripted model")

    # Journey 1 -----------------------------------------------------------------------

    async def gold_agent_trades_on_its_own(self) -> str:
        """«أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه، وخسارة يومية قصوى 2%»: one grant
        card, one passkey; the agent then trades by itself, and a worker that dies mid-send
        never sends it twice."""
        name = "J1 create a gold agent and let it trade on its own"
        words = "أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه، وخسارة يومية قصوى 2%"
        task = "يدير صفقات الذهب على حساب المالك بنفسه ضمن التفويض الموقّع."
        self.model.script(
            words,
            lambda t: call(
                "j1-create",
                "agent_create",
                {
                    "template": "trading",
                    "name": "Gold agent",
                    "market": "XAUUSD",
                    "responsibility": task,
                },
            ),
            lambda t: call(
                "j1-grant",
                "owner_action_propose",
                {
                    "kind": "grant_authority",
                    "agent_id": t.result("j1-create")["agent"]["id"],
                    "daily_loss_percent": "2",
                },
            ),
            "أنشأت وكيل الذهب على XAUUSD، وهو يسألك قبل كل صفقة حتى توقّع بطاقة التفويض.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        async with self.db.sessions() as session:
            agents = list(
                await session.scalars(
                    select(AgentRow).where(
                        AgentRow.owner_id == self.owner, AgentRow.name.like("Gold agent%")
                    )
                )
            )
        assert len(agents) == 1, [agent.name for agent in agents]
        gold = agents[0]
        self.created.append(gold.id)
        assert (gold.trading_account_id, gold.trading_symbol) == (self.account, GOLD)
        # Created by the owner's sentence: no question, no grant, Ask me.
        assert await self.level(gold.id) == "supervised"
        assert await self.count(AccountAuthorityRow, AccountAuthorityRow.agent_id == gold.id) == 0
        created = await self.pending(self.lonora_thread, "agent_created")
        assert len(created) == 1 and created[0]["facts"]["undo"] == "delete", created
        grant_cards = await self.pending(self.lonora_thread, "grant_authority")
        assert len(grant_cards) == 1, grant_cards
        card = grant_cards[0]
        grant = card["facts"]["grant"]
        assert grant["symbols"] == [GOLD] and grant["symbol_scope"] == "selected", grant
        assert grant["duration"] == "until_stopped" and grant["all_actions"] is True
        assert grant["allow_manual_positions"] is False  # D1: the owner's own excluded.
        daily = card["facts"]["money"]["daily_loss"]
        assert daily["proposed"] == "200.00" and daily["basis"] == "requested", daily
        assert card["requires_passkey"] is True
        # Nothing trades before the signature: the agent is still Ask me.
        state = await self.state(gold.id)
        assert state["trading_readiness"]["state"] == "ask_me", state
        # One tap on Authorize with the passkey (the device enrolls inline the first time).
        decided = await self.passkey(name, card["id"], {})
        assert decided["status"] == "confirmed", decided
        assert decided["result"]["daily_loss"] == "200.00"
        assert await self.level(gold.id) == "autonomous"
        policy = await self.request("GET", f"/trading/accounts/{self.account}/execution-policy")
        assert Decimal(policy["risk"]["max_daily_loss"]) == 200
        # The status line, the card and the records agree.
        readiness = (await self.state(gold.id))["trading_readiness"]
        assert readiness["state"] == "on_its_own", readiness
        assert readiness["params"]["symbols"] == [GOLD], readiness["params"]
        assert readiness["params"]["money_limit_set"] is True
        assert readiness["params"].get("daily_loss") == {"amount": "200.00", "currency": "USD"}, (
            readiness["params"]
        )
        assert readiness["grants"][0]["allow_manual_positions"] is False
        async with self.db.sessions() as session:
            active = list(
                await session.scalars(
                    select(AccountAuthorityRow).where(
                        AccountAuthorityRow.agent_id == gold.id,
                        AccountAuthorityRow.status == "active",
                    )
                )
            )
        assert len(active) == 1 and active[0].envelope["symbols"] == [GOLD]
        # Lonora confirms in one Arabic line in the conversation where the owner asked.
        line = (await self.lines(self.lonora_thread))[-1]
        assert any("؀" <= char <= "ۿ" for char in line), line
        # The agent starts its responsibility: one management Task in its conversation.
        management = [
            row
            for row in await self.runs(gold.id)
            if row.model_metadata.get("account_management_id") == active[0].id
        ]
        assert len(management) == 1 and management[0].status == "queued", management
        self.journey(name, 1)

        # The management Task: the agent buys gold on its own (no tap); the worker dies
        # after the broker took the order and before it heard back.
        cached = self.services.brokers.connections[self.account]
        dying = CrashAfterSend(self.db, self.owner, self.account)
        dying.reached = asyncio.Event()
        self.services.brokers.connections[self.account] = (cached[0], dying)
        order = {
            "action": "buy",
            "account_id": self.account,
            "symbol": GOLD,
            "volume": "0.1",
            "stop_loss": "1990",
        }
        script = self.model.script(
            "The owner has authenticated automatic management of account",
            lambda t: call("j1-buy", "trade_execute", order),
            # After the restart the model sees its order as uncertain and, careless, asks
            # for the same order again under a new call: it must not reach the broker.
            lambda t: call("j1-buy-again", "trade_execute", order),
            lambda t: ModelReply(
                text="أمر الشراء الأول بانتظار تأكيد الوسيط، ولن أرسله مرة أخرى.",
                tool_calls=[
                    ToolCall(
                        id="j1-wait", name="task_wait", arguments={"kind": "timer", "seconds": 3600}
                    )
                ],
            ),
        )
        before = len(await self.positions(self.account))
        await self.refresh_quotes(self.account)
        try:
            restarted = await self.crash_and_restart(management[0].id, dying.reached)
        finally:
            self.services.brokers.connections[self.account] = cached
        assert script.attempts.get(0) == 1, script.attempts  # The order was asked for once.
        transcript = self.model.sent[-1]
        uncertain = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j1-buy")
        )
        # The interrupted send comes back uncertain, never as sent or failed: either the
        # in-flight marker survived (tool_execution_uncertain) or the executor recorded the
        # broker result as ambiguous while the worker stopped.
        assert uncertain.get("reason") == "tool execution uncertain" or (
            uncertain.get("status") == "ambiguous"
            and uncertain["recovery"]["next_action"] == "reconcile before any resend"
        ), uncertain
        again = json.loads(
            next(
                m.content
                for m in transcript
                if m.role == "tool" and m.tool_call_id == "j1-buy-again"
            )
        )
        # The same order again in this Run is the same operation: its uncertain receipt
        # comes back, it is never sent a second time.
        assert again.get("status") == "ambiguous", again
        assert again.get("operation_id") == uncertain.get("operation_id"), (again, uncertain)
        opened = [p for p in await self.positions(self.account) if p["symbol"] == GOLD]
        assert len(opened) == before + 1, opened  # Exactly one order reached the broker.
        async with self.db.sessions() as session:
            rows = list(
                await session.scalars(
                    select(TradingJournalRow).where(
                        TradingJournalRow.account_id == self.account,
                        TradingJournalRow.request["symbol"].as_string() == GOLD,
                        TradingJournalRow.status.not_in(["failed"]),
                    )
                )
            )
        assert len(rows) == 1 and rows[0].status in {"submitted", "ambiguous"}, [
            r.status for r in rows
        ]
        # While it is unsettled the line says so; reconciliation then reads the broker
        # (observe only, never a resend) and confirms the one order.
        readiness = (await self.state(gold.id))["trading_readiness"]
        assert readiness["state"] == "uncertain" and readiness["params"]["symbol"] == GOLD, (
            readiness
        )
        async with self.db.sessions() as session, session.begin():
            row = await session.get(TradingJournalRow, rows[0].operation_id, with_for_update=True)
            assert row is not None and row.submitted_at is not None
            row.submitted_at -= timedelta(minutes=2)  # Past the submission grace.
        await reconcile_ambiguous(self.db, self.services.brokers)
        async with self.db.sessions() as session:
            settled = await session.get(
                TradingJournalRow, rows[0].operation_id, populate_existing=True
            )
            assert settled is not None and settled.status == "confirmed", settled and settled.status
        assert (
            len([p for p in await self.positions(self.account) if p["symbol"] == GOLD])
            == before + 1
        )
        readiness = (await self.state(gold.id))["trading_readiness"]
        assert readiness["state"] == "on_its_own", readiness
        print(
            "PASS the gold agent trades on its own; a worker that dies mid-send is continued by "
            "another, the order reaches the broker once and is confirmed by reconciliation"
        )
        del restarted
        return gold.id

    # Journey 11 ----------------------------------------------------------------------

    async def approve_one_trade(self) -> None:
        """Lonora is at Ask me: «اشترِ 0.1 يورو دولار» becomes one approval card with
        labeled values; nothing reaches the broker before the owner's tap."""
        name = "J11 approve one trade from an agent set to Ask me"
        words = "اشترِ 0.1 يورو دولار على حسابي بوقف خسارة 1.0900"
        order = {
            "action": "buy",
            "account_id": self.account,
            "symbol": EURO,
            "volume": "0.1",
            "stop_loss": "1.0900",
        }
        self.model.script(
            words,
            lambda t: call("j11-buy", "trade_execute", order),
            lambda t: ModelReply(
                text="نُفّذ الشراء بعد موافقتك."
                if t.result("j11-buy").get("status") == "confirmed"
                else "لم يُنفّذ الأمر."
            ),
        )
        assert await self.level(self.lonora) == "supervised"
        await self.refresh_quotes(self.account)
        before = [p for p in await self.positions(self.account) if p["symbol"] == EURO]
        run_id = await self.say(self.lonora_thread, words)
        waiting = await self.work(run_id)
        assert waiting.status == "waiting_input", (waiting.status, waiting.error_code)
        approvals = cast(
            list[dict[str, Any]],
            await self.request("GET", f"/trading/approvals?thread_id={self.lonora_thread}"),
        )
        mine = [
            item for item in approvals if item["run_id"] == run_id and item["status"] == "pending"
        ]
        assert len(mine) == 1, approvals
        approval = mine[0]
        requested = approval["requests"][0]
        assert (requested["action"], requested["symbol"], str(requested["volume"])) == (
            "buy",
            EURO,
            "0.1",
        ), requested
        assert approval["thread_id"] == self.lonora_thread and approval["timeline_seq"] is not None
        # Nothing trades without the tap.
        assert [p for p in await self.positions(self.account) if p["symbol"] == EURO] == before
        await self.request(
            "POST", f"/trading/approvals/{approval['id']}/decision", {"decision": "approve"}
        )
        self.tap(name)
        await self.refresh_quotes(self.account)
        done = await self.work(run_id)
        assert done.status == "completed", (done.status, done.error_code)
        bought = [p for p in await self.positions(self.account) if p["symbol"] == EURO]
        assert len(bought) == len(before) + 1, bought
        decided = cast(
            list[dict[str, Any]],
            await self.request("GET", f"/trading/approvals?thread_id={self.lonora_thread}"),
        )
        record = next(item for item in decided if item["id"] == approval["id"])
        # The result line comes from the broker's evidence: confirmed with its ticket.
        result = record["results"][0]
        assert result["status"] == "confirmed" and result["broker_id"], result
        async with self.db.sessions() as session:
            journal = await session.get(TradingJournalRow, result["operation_id"])
            assert journal is not None and journal.status == "confirmed"
            assert journal.result["broker_id"] == result["broker_id"]
        self.journey(name, 1)

    # Journey 2 -----------------------------------------------------------------------

    async def lonora_manages_all_pairs(self) -> None:
        """«خلي لونورا تدير كل أزواجي بنفسها»: one grant card per connected account with
        all pairs preselected and the account's money limits; a broker event on one of its
        positions wakes Lonora with its normal authority."""
        name = "J2 let Lonora manage all my pairs"
        connection = await self.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "acc-second-" + uuid4().hex, "enabled": True},
        )
        self.second_account = connection["id"]
        await self.request(
            "POST",
            f"/trading/connections/{self.second_account}/simulation",
            {"snapshot": snapshot()},
        )
        await self.services.brokers.get(self.owner, self.second_account)
        words = "خلي لونورا تدير كل أزواجي بنفسها"
        self.model.script(
            words,
            lambda t: calls(
                (
                    "j2-first",
                    "owner_action_propose",
                    {"kind": "grant_authority", "account_id": self.account},
                ),
                (
                    "j2-second",
                    "owner_action_propose",
                    {"kind": "grant_authority", "account_id": self.second_account},
                ),
            ),
            "جهّزت بطاقة تفويض لكل حساب: كل الأزواج، حتى توقفه، مع حدودك المالية.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        cards = await self.pending(self.lonora_thread, "grant_authority")
        assert len(cards) == 2, cards
        by_account = {card["facts"]["account"]["id"]: card for card in cards}
        assert set(by_account) == {self.account, self.second_account}
        for card in cards:
            grant = card["facts"]["grant"]
            assert grant["symbol_scope"] == "account" and grant["agent_is_personal"] is True
            assert grant["allow_manual_positions"] is False
        # The first account keeps the owner's 200 limit; the second gets the D1 suggestion.
        first = by_account[self.account]["facts"]["money"]["daily_loss"]
        assert Decimal(first["current"]) == 200 and first["proposed"] is None, first
        second = by_account[self.second_account]["facts"]["money"]["daily_loss"]
        assert second["proposed"] == "300.00" and second["basis"] == "suggested", second
        # The gold agent already trades gold on the first account: the card says so.
        names = [item["agent_name"] for item in by_account[self.account]["facts"]["conflicts"]]
        assert names == ["Gold agent"], names
        for card in cards:
            decided = await self.passkey(name, card["id"], {})  # Keep both agents.
            assert decided["status"] == "confirmed", decided
        assert await self.level(self.lonora) == "autonomous"
        readiness = (await self.state(self.lonora))["trading_readiness"]
        assert readiness["state"] == "on_its_own" and readiness["params"]["grant_count"] == 2
        assert readiness["params"]["symbol_scope"] == "account"
        assert await self.level(self.created[0]) == "autonomous"  # "Keep both".
        self.journey(name, 2)  # One per connected account; here there are two.

        # Lonora trades on its own now, then the broker closes the position at its stop.
        words = "افتح شراء 0.1 يورو دولار على الحساب الثاني بوقف خسارة 1.0900"
        self.model.script(
            words,
            lambda t: call(
                "j2-buy",
                "trade_execute",
                {
                    "action": "buy",
                    "account_id": self.second_account,
                    "symbol": EURO,
                    "volume": "0.1",
                    "stop_loss": "1.0900",
                },
            ),
            "فتحت الصفقة.",
        )
        await self.refresh_quotes(self.second_account)
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        opened = [p for p in await self.positions(self.second_account) if p["symbol"] == EURO]
        assert len(opened) == 1, opened  # No tap: the signed grant covers it.
        brokers = self.services.brokers
        await reconcile_broker_account(self.db, brokers, self.owner, self.second_account)
        async with self.db.sessions() as session, session.begin():
            book = await session.get(TradingAccountRow, self.second_account, with_for_update=True)
            assert book is not None
            book.payload = {
                **book.payload,
                "positions": [p for p in book.payload["positions"] if p["symbol"] != EURO],
            }
        await reconcile_broker_account(self.db, brokers, self.owner, self.second_account)
        wakes = [
            row
            for row in await self.runs(self.lonora, "broker_event")
            if row.model_metadata.get("account_id") == self.second_account
        ]
        assert len(wakes) == 1, [row.model_metadata for row in wakes]
        assert "authority" not in wakes[0].model_metadata  # Normal authority, not observe-only.
        await reconcile_broker_account(self.db, brokers, self.owner, self.second_account)
        assert (
            len(
                [
                    row
                    for row in await self.runs(self.lonora, "broker_event")
                    if row.model_metadata.get("account_id") == self.second_account
                ]
            )
            == 1
        )
        print("PASS a stop-loss hit on Lonora's own position wakes Lonora once, with its authority")

    # Journey 10 (start) ---------------------------------------------------------------

    async def watch_london_session(self) -> str:
        """«راقب الذهب خلال جلسة لندن اليوم»: one watch with the session's expiry; the
        status line says what it watches and until when. A worker that dies after the
        watch was saved, and a model that then asks for it again, leave one watch."""
        name = "J10 watch gold during the London session, then stop watching"
        words = "راقب الذهب خلال جلسة لندن اليوم"
        until = next_london_close()
        watch = {
            "kind": "price",
            "account_id": self.account,
            "symbol": GOLD,
            "condition": "above",
            "level": "2010",
            "prompt": "Gold broke above 2010 during the London session: reassess.",
            "expires_at": until,
        }
        reached = asyncio.Event()
        self.model.script(
            words,
            lambda t: call("j10-watch", "watch_create", watch),
            crash_then(reached, lambda t: call("j10-watch-again", "watch_create", watch)),
            "أراقب الذهب حتى إغلاق جلسة لندن.",
        )
        run = await self.crash_and_restart(await self.say(self.lonora_thread, words), reached)
        assert run.status == "completed", (run.status, run.error_code)
        async with self.db.sessions() as session:
            watches = list(
                await session.scalars(
                    select(MarketWatchRow).where(
                        MarketWatchRow.agent_id == self.lonora,
                        MarketWatchRow.payload["enabled"].as_boolean().is_(True),
                    )
                )
            )
        assert len(watches) == 1, [row.payload for row in watches]  # Never a second watch.
        state = await self.state(self.lonora)
        assert state["phase"] == "monitoring" and state["reason_code"] == "market_watch", state
        shown = state["watches"]
        assert len(shown) == 1 and shown[0]["symbol"] == GOLD and shown[0]["expires_at"], shown
        assert "prompt" not in shown[0]
        print("PASS the watch is saved once with the session's expiry; the status line shows it")
        self.watch_name = name
        return watches[0].id

    # Journey 3 -----------------------------------------------------------------------

    async def pause_today_then_resume(self, watch_id: str) -> None:
        """«أوقف فتح صفقات جديدة اليوم، وكمّل مراقبة الذهب»: one restriction for all agents
        until the end of the day, the watch keeps running, one Lift card; one tap resumes."""
        name = "J3 stop new trades today, then resume later"
        words = "أوقف فتح صفقات جديدة اليوم، وكمّل مراقبة الذهب"
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        end_of_day = datetime.combine(
            datetime.now(ZoneInfo("UTC")).date(), time(23, 59, 59), ZoneInfo("UTC")
        ).isoformat()
        self.model.script(
            words,
            lambda t: call(
                "j3-pause",
                "trade_restriction_create",
                {
                    "account_id": self.account,
                    "all_symbols": True,
                    "all_agents": True,
                    "action_class": "no_new_entries",
                    "valid_until": end_of_day,
                    "reason": "The owner asked: no new trades today; keep watching gold.",
                },
            ),
            "أوقفت الصفقات الجديدة لكل الوكلاء حتى نهاية اليوم؛ الإغلاق وتقريب الوقف مسموحان، "
            "ومراقبة الذهب مستمرة.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        restriction_id = json.loads(
            next(
                m.content
                for m in self.model.sent[-1]
                if m.role == "tool" and m.tool_call_id == "j3-pause"
            )
        )["restriction"]["id"]
        async with self.db.sessions() as session:
            restriction = await session.get(TradingRestrictionRow, restriction_id)
            assert restriction is not None and restriction.agent_id is None
            assert restriction.source == "owner_message" and restriction.revoked_at is None
            watch = await session.get(MarketWatchRow, watch_id, populate_existing=True)
            assert watch is not None and watch.payload["enabled"] is True  # Still watching.
        await self.project()
        lifts = await self.pending(self.lonora_thread, "lift_restriction")
        assert len(lifts) == 1, lifts
        facts = lifts[0]["facts"]["restriction"]
        assert facts["action_class"] == "no_new_entries" and facts["valid_until"], facts
        # The pill on every agent says the same thing as the card and the record.
        for agent_id in (self.lonora, self.created[0]):
            readiness = (await self.state(agent_id))["trading_readiness"]
            assert readiness["state"] == "paused", (agent_id, readiness)
            assert readiness["params"]["action_class"] == "no_new_entries"
            assert readiness["params"]["valid_until"] == facts["valid_until"]
            assert readiness["exits_allowed"] is True
        # A new entry is held; nothing reaches the broker.
        before = await self.positions(self.account)
        self.model.script(
            "اشترِ 0.01 ذهب الآن",
            lambda t: call(
                "j3-buy",
                "trade_execute",
                {
                    "action": "buy",
                    "account_id": self.account,
                    "symbol": GOLD,
                    "volume": "0.01",
                    "stop_loss": "1990",
                },
            ),
            "الصفقات الجديدة متوقفة اليوم بطلبك.",
        )
        await self.refresh_quotes(self.account)
        refused = await self.work(await self.say(self.lonora_thread, "اشترِ 0.01 ذهب الآن"))
        assert refused.status == "completed", (
            refused.status,
            refused.error_code,
            [m.content[:300] for m in self.model.sent[-1][-2:]],
        )
        result = json.loads(
            next(
                m.content
                for m in self.model.sent[-1]
                if m.role == "tool" and m.tool_call_id == "j3-buy"
            )
        )
        # Refused with the pause's own code before any approval card (Lonora is Ask me).
        assert result.get("ok") is False and result.get("reason") == "trading restriction active", (
            result
        )
        assert await self.count(TradeApprovalRow, TradeApprovalRow.run_id == refused.id) == 0
        assert await self.positions(self.account) == before
        # Later the owner says «رجّع التداول»: Lonora offers the Lift card (the same one).
        self.model.script(
            "رجّع التداول",
            lambda t: call(
                "j3-lift",
                "owner_action_propose",
                {"kind": "lift_restriction", "restriction_id": restriction_id},
            ),
            "اضغط «رفع الإيقاف» على البطاقة.",
        )
        run = await self.work(await self.say(self.lonora_thread, "رجّع التداول"))
        assert run.status == "completed"
        again = await self.pending(self.lonora_thread, "lift_restriction")
        assert [card["id"] for card in again] == [lifts[0]["id"]], again  # No second card.
        lifted = await self.decide(name, lifts[0]["id"], {"decision": "confirm"})
        assert lifted["status"] == "confirmed" and lifted["decided_via"] == "tap", lifted
        async with self.db.sessions() as session:
            restriction = await session.get(
                TradingRestrictionRow, restriction_id, populate_existing=True
            )
            assert restriction is not None and restriction.revoked_at is not None
        assert (await self.state(self.lonora))["trading_readiness"]["state"] == "on_its_own" or (
            await self.level(self.lonora)
        ) == "supervised"
        line = (await self.lines(self.lonora_thread))[-1]
        assert any("\u0600" <= char <= "\u06ff" for char in line), line
        self.journey(name, 1)

    # Journey 10 (end) ----------------------------------------------------------------

    async def stop_watching(self, watch_id: str) -> None:
        """«وقف مراقبة الذهب»: the agent cancels its own watch and says so, with Undo."""
        words = "وقف مراقبة الذهب"
        self.model.script(
            words,
            lambda t: call("j10-cancel", "watch_cancel", {"watch_id": watch_id}),
            "أوقفت مراقبة الذهب. يمكنك التراجع.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        result = json.loads(
            next(
                m.content
                for m in self.model.sent[-1]
                if m.role == "tool" and m.tool_call_id == "j10-cancel"
            )
        )
        assert result["payload"]["enabled"] is False and result["undo"] == "watch_resume", result
        state = await self.state(self.lonora)
        assert state["watches"] == [] and state.get("watch_count", 0) == 0, state
        self.journey(self.watch_name, 0)

    # Journey 3, two accounts ----------------------------------------------------------

    async def pause_every_account(self) -> None:
        """With two accounts a pause for "today" is one restriction and one Lift card per
        account (a restriction is scoped to one account); lifting is one tap per account."""
        name = "J3b stop new trades today on two accounts, then resume"
        words = "أوقف الصفقات الجديدة اليوم على كل حساباتي"
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        end_of_day = datetime.combine(
            datetime.now(ZoneInfo("UTC")).date(), time(23, 59, 59), ZoneInfo("UTC")
        ).isoformat()

        def pause(call_id: str, account: str) -> tuple[str, str, dict[str, Any]]:
            return (
                call_id,
                "trade_restriction_create",
                {
                    "account_id": account,
                    "all_symbols": True,
                    "all_agents": True,
                    "action_class": "no_new_entries",
                    "valid_until": end_of_day,
                    "reason": "The owner asked: no new trades today on every account.",
                },
            )

        self.model.script(
            words,
            lambda t: calls(
                pause("j3b-first", self.account), pause("j3b-second", self.second_account)
            ),
            "أوقفت الصفقات الجديدة على الحسابين حتى نهاية اليوم.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        await self.project()
        lifts = await self.pending(self.lonora_thread, "lift_restriction")
        assert len(lifts) == 2, lifts
        assert (await self.state(self.lonora))["trading_readiness"]["state"] == "paused"
        for card in lifts:
            await self.decide(name, card["id"], {"decision": "confirm"})
        assert (await self.state(self.lonora))["trading_readiness"]["state"] == "on_its_own"
        self.journey(name, 2, "one Lift card per account; the journey list assumes one account")

    # Journey 7 -----------------------------------------------------------------------

    async def resolve_uncertain_trade(self) -> None:
        """An order the broker never confirmed: an "Action needed" item and one card in the
        agent's conversation; one tap settles it, the hold clears, nothing is resent."""
        name = "J7 resolve an uncertain trade"
        gold_id = self.created[0]
        gold_thread = await self.conversation(gold_id)
        words = "اشترِ 0.1 ذهب الآن بوقف خسارة 1990"
        self.model.script(
            words,
            lambda t: call(
                "j7-buy",
                "trade_execute",
                {
                    "action": "buy",
                    "account_id": self.account,
                    "symbol": GOLD,
                    "volume": "0.1",
                    "stop_loss": "1990",
                },
            ),
            "لم يؤكد الوسيط الأمر بعد، ولن أرسله مرة أخرى.",
        )

        class Unconfirmable(LostAcknowledgement):
            async def reconcile(
                self, operation_id: str, request: Any = None, **_: Any
            ) -> TradeResult:
                return TradeResult(
                    operation_id=operation_id, status="ambiguous", code="execution_not_observed"
                )

        cached = self.services.brokers.connections[self.account]
        self.services.brokers.connections[self.account] = (
            cached[0],
            Unconfirmable(self.db, self.owner, self.account),
        )
        await self.refresh_quotes(self.account)
        before = len(await self.positions(self.account))
        try:
            run = await self.work(await self.say(gold_thread, words))
        finally:
            self.services.brokers.connections[self.account] = cached
        assert run.status == "completed", (run.status, run.error_code)
        result = json.loads(
            next(
                m.content
                for m in self.model.sent[-1]
                if m.role == "tool" and m.tool_call_id == "j7-buy"
            )
        )
        assert result["status"] == "ambiguous", result
        operation = result["operation_id"]
        assert len(await self.positions(self.account)) == before + 1  # It did reach the broker.
        await self.project()
        cards = await self.pending(gold_thread, "resolve_operation")
        assert len(cards) == 1, cards
        facts = cards[0]["facts"]["operation"]
        assert (facts["symbol"], facts["action"], str(facts["volume"])) == (GOLD, "buy", "0.1"), (
            facts
        )
        assert facts["by_agent_name"] == "Gold agent", facts
        async with self.db.sessions() as session:
            items = list(
                await session.scalars(
                    select(AttentionRow).where(
                        AttentionRow.owner_id == self.owner,
                        AttentionRow.code == "operation_uncertain",
                        AttentionRow.status == "ready",
                    )
                )
            )
        assert len(items) == 1 and items[0].importance == "action_required", items
        readiness = (await self.state(gold_id))["trading_readiness"]
        assert readiness["state"] == "uncertain" and readiness["params"]["symbol"] == GOLD
        # One tap: "It executed". No statement is needed.
        answered = await self.decide(
            name, cards[0]["id"], {"decision": "confirm", "outcome": "executed"}
        )
        assert answered["status"] == "confirmed", answered
        async with self.db.sessions() as session:
            journal = await session.get(TradingJournalRow, operation, populate_existing=True)
            assert journal is not None and journal.status == "resolved"
            resolution = journal.result["details"]["resolution"]
            assert resolution["outcome"] == "executed" and resolution["broker_confirmed"] is False
        assert (await self.state(gold_id))["trading_readiness"]["state"] == "on_its_own"
        line = (await self.lines(gold_thread))[-1]
        assert "ليس تأكيدًا من الوسيط" in line, line  # Back in the same conversation.
        await self.project()
        async with self.db.sessions() as session:
            item = await session.get(AttentionRow, items[0].id, populate_existing=True)
            assert item is not None and item.status == "suppressed"
        assert len(await self.positions(self.account)) == before + 1  # Never resent.
        self.journey(name, 1)

    # MCP (D3): the owner's secure form, then his words trust it ------------------------

    async def connect_mcp(
        self, journey: str, card_id: str, name: str, token: str | None, url: str = MCP_URL
    ) -> str:
        """The secure card's form posts the token and server straight to the owner API (one
        tap: Connect); then the owner names the server in chat and Lonora trusts its tools
        (VISION 10.3.2: no card)."""
        secret_id = None
        if token is not None:
            secret_id = (
                await self.request("POST", "/integrations/secrets", {"name": name, "value": token})
            )["id"]
        server = await self.request(
            "POST",
            "/mcp",
            {
                "payload": {
                    "name": name,
                    "transport": "http",
                    "url": url,
                    "secret_id": secret_id,
                    "enabled": True,
                },
                "agent_id": None,
                "thread_id": None,
            },
        )
        connected = await self.decide(
            journey,
            card_id,
            {"decision": "confirm", "connected": {"resource": "mcp", "id": server["id"]}},
        )
        assert connected["status"] == "confirmed" and connected["result"]["configured"], connected
        # Lonora continues after the card (and asks the owner to name the server).
        for queued in await self.runs(self.lonora, "owner_card"):
            if queued.status == "queued":
                await self.work(queued.id)
        words = "ثق بخادم " + name
        trusted: dict[str, Any] = {}

        def done(t: Turn) -> ModelReply:
            trusted.update(t.result("trust-" + name))
            return ModelReply(text="وثقت بأدوات الخادم للقراءة.")

        self.model.script(
            words, lambda t: call("trust-" + name, "mcp_trust", {"server": name}), done
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        assert trusted["trusted"] is True and trusted["tier"] == "read", trusted
        assert trusted["tools_trusted"] == 1 and trusted["tools_blocked_moving_money"] == 1
        async with self.db.sessions() as session:
            row = await session.scalar(
                select(TrustedSourceRow).where(
                    TrustedSourceRow.identifier == server["id"],
                    TrustedSourceRow.revoked_at.is_(None),
                )
            )
            assert row is not None and row.added_via == "owner_message", row
        assert await self.pending(self.lonora_thread, "trust_source") == []
        return cast(str, server["id"])

    # Journey 4 -----------------------------------------------------------------------

    async def news_agent_and_supervisor(self) -> tuple[str, str, str]:
        """«أنشئ وكيل أخبار ... وخلي وكيل ثاني يشرف عليهم»: one news agent that reports to
        the gold agent, one supervisor over both, one "Connect X" card; a worker that dies
        mid-turn and a model that then repeats itself add nothing."""
        name = "J4 create a news agent and a supervisor"
        gold_id = self.created[0]
        words = (
            "أنشئ وكيل أخبار يتابع الأخبار الاقتصادية ومحللي X ويبلغ وكيل الذهب بالمهم، "
            "وخلي وكيل ثاني يشرف عليهم"
        )
        news_spec = {
            "template": "research",
            "name": "News agent",
            "responsibility": "يتابع الأخبار الاقتصادية ومحللي X ويبلغ وكيل الذهب بالمهم.",
            "report_to": [gold_id],
        }

        def supervisor(t: Turn, call_id: str = "j4-news") -> dict[str, Any]:
            return {
                "template": "supervisor",
                "name": "Desk supervisor",
                "responsibility": "يشرف على وكيل الأخبار ووكيل الذهب.",
                "supervises": [t.result(call_id)["agent"]["id"], gold_id],
            }

        reached = asyncio.Event()
        self.model.script(
            words,
            lambda t: call("j4-news", "agent_create", news_spec),
            lambda t: call("j4-supervisor", "agent_create", supervisor(t)),
            crash_then(
                reached,
                lambda t: calls(
                    # The restarted model asks for both agents again, under new calls.
                    ("j4-news-again", "agent_create", news_spec),
                    ("j4-supervisor-again", "agent_create", supervisor(t)),
                    (
                        "j4-connect-x",
                        "owner_action_propose",
                        {"kind": "connect_credential", "target": "mcp_server", "service": "x"},
                    ),
                ),
            ),
            "أنشأت وكيل الأخبار ووكيل الإشراف. الأخبار والتقويم الاقتصادي يعملان الآن؛ "
            "اربط X من البطاقة.",
        )
        run = await self.crash_and_restart(await self.say(self.lonora_thread, words), reached)
        assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        news_result = json.loads(
            next(
                m.content
                for m in transcript
                if m.role == "tool" and m.tool_call_id == "j4-news-again"
            )
        )
        assert news_result["deduplicated"] is True, news_result
        async with self.db.sessions() as session:
            news = list(
                await session.scalars(
                    select(AgentRow).where(
                        AgentRow.owner_id == self.owner, AgentRow.name.like("News agent%")
                    )
                )
            )
            desk = list(
                await session.scalars(
                    select(AgentRow).where(
                        AgentRow.owner_id == self.owner, AgentRow.name.like("Desk supervisor%")
                    )
                )
            )
        assert len(news) == 1 and len(desk) == 1, ([a.name for a in news], [a.name for a in desk])
        news_id, desk_id = news[0].id, desk[0].id
        self.created.extend([news_id, desk_id])
        assert await self.level(news_id) == "analysis" and await self.level(desk_id) == "analysis"
        directory = {item["id"]: item for item in (await self.request("GET", "/agents"))}
        del directory
        async with self.db.sessions() as session:
            grants = list(
                await session.scalars(
                    select(SupervisionGrantRow).where(
                        SupervisionGrantRow.supervisor_agent_id == desk_id,
                        SupervisionGrantRow.revoked_at.is_(None),
                    )
                )
            )
            assert sorted(g.supervised_agent_id for g in grants) == sorted([news_id, gold_id]), (
                grants
            )
            assert all(g.created_via == "owner_message" and g.source_message_id for g in grants), (
                grants
            )
            lonora_over = await session.scalar(
                select(func.count())
                .select_from(SupervisionGrantRow)
                .where(
                    SupervisionGrantRow.supervisor_agent_id == self.lonora,
                    SupervisionGrantRow.supervised_agent_id.in_([news_id, desk_id]),
                    SupervisionGrantRow.revoked_at.is_(None),
                )
            )
            assert lonora_over == 2, lonora_over  # Lonora sees them by default.
        cards = await self.cards(self.lonora_thread)
        created = [
            c
            for c in cards
            if c["kind"] == "agent_created"
            and c["facts"]["agent"]["name"] in {"News agent", "Desk supervisor"}
        ]
        assert len(created) == 2, created  # One Undo card each, never two.
        connect = [
            c for c in cards if c["kind"] == "connect_credential" and c["status"] == "pending"
        ]
        assert len(connect) == 1 and connect[0]["facts"]["credential"]["service"] == "x", connect
        assert (
            await self.count(
                AccountAuthorityRow, AccountAuthorityRow.agent_id.in_([news_id, desk_id])
            )
            == 0
        )
        # D3: X through an MCP server the owner trusts; the token never leaves the server.
        seen: list[str] = []
        tokens: list[str | None] = []
        with patch.object(mcp, "HttpMcpTransport", x_server(seen, tokens)):
            connection = await self.connect_mcp(name, connect[0]["id"], "X", MCP_TOKEN)
            # The news agent reads X on its own next sweep, and tells the gold agent.
            news_thread = await self.conversation(news_id)
            sweep = "صباح الخير، ما المهم في الأخبار و X اليوم؟"
            self.model.script(
                sweep,
                lambda t: calls(
                    (
                        "j4-x",
                        "mcp_execute",
                        {
                            "connection_id": connection,
                            "name": "search_posts",
                            "arguments": {"query": "gold analysts"},
                        },
                    ),
                    ("j4-calendar", "economic_calendar_read", {}),
                ),
                lambda t: call(
                    "j4-tell-gold",
                    "peer_send",
                    {
                        "agent_id": gold_id,
                        "task": "Analysts expect gold bid into CPI; review your plan.",
                    },
                ),
                "أبلغت وكيل الذهب بأهم ما قاله المحللون.",
            )
            run = await self.work(await self.say(news_thread, sweep))
            assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        x = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j4-x")
        )
        assert "Analyst: gold bid into CPI" in json.dumps(x, ensure_ascii=False), x
        assert seen.count("tools/call") == 1 and MCP_TOKEN in tokens  # Server side only.
        told = json.loads(
            next(
                m.content
                for m in transcript
                if m.role == "tool" and m.tool_call_id == "j4-tell-gold"
            )
        )
        assert told.get("ok") is not False, told
        # The gold agent gets the message as its own run, and its answer comes back to the
        # news agent (a follow-up run), as a gateway worker would process them.
        self.model.script(
            "Analysts expect gold bid into CPI",
            "سأراجع خطة الذهب قبل بيانات التضخم.",
        )
        for agent_id in (gold_id, news_id):
            for queued in [
                r
                for r in await self.runs(agent_id)
                if r.status == "queued" and r.trigger != "routine"
            ]:
                if queued.model_metadata.get("account_management_id"):
                    continue  # The gold agent's waiting management Task is not due.
                done = await self.work(queued.id)
                assert done.status in {"completed", "waiting_input"}, (done.trigger, done.status)
        peer = [
            r for r in await self.runs(gold_id) if "Analysts expect gold bid into CPI" in r.prompt
        ]
        assert len(peer) == 1, [r.prompt[:80] for r in await self.runs(gold_id)]
        # One owner step: a new credential (one secure card). The source outside the
        # trusted list is trusted by the owner's own words, no card (VISION 10.3.2).
        self.journey(name, 1)
        return news_id, desk_id, connection

    # Journey 6 -----------------------------------------------------------------------

    async def add_mcp_server(self) -> None:
        """«أضف خادم MCP هذا» with its URL: one secure card for the server (and its token, if
        any), then the owner names it in chat; every agent then uses its tools with no
        declaration and no further card, and a tool that could trade is never trusted."""
        name = "J6 add an MCP server"
        words = "أضف خادم MCP هذا: " + NOTES_URL
        self.model.script(
            words,
            lambda t: call(
                "j6-connect",
                "owner_action_propose",
                {"kind": "connect_credential", "target": "mcp_server"},
            ),
            "اربط الخادم من البطاقة؛ سأعرض أدواته لتثق بها.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        cards = await self.pending(self.lonora_thread, "connect_credential")
        assert len(cards) == 1, cards
        seen: list[str] = []
        with patch.object(mcp, "HttpMcpTransport", x_server(seen, [])):
            connection = await self.connect_mcp(name, cards[0]["id"], "Notes", None, NOTES_URL)
            gold_id = self.created[0]
            gold_thread = await self.conversation(gold_id)
            ask = "ابحث في ملاحظات الخادم الجديد عن الذهب"
            self.model.script(
                ask,
                lambda t: call(
                    "j6-search",
                    "mcp_execute",
                    {
                        "connection_id": connection,
                        "name": "search_posts",
                        "arguments": {"query": "gold"},
                    },
                ),
                lambda t: call(
                    "j6-order",
                    "mcp_execute",
                    {
                        "connection_id": connection,
                        "name": "place_order",
                        "arguments": {"query": "buy"},
                    },
                ),
                "وجدت ملاحظة عن الذهب قبل بيانات التضخم.",
            )
            run = await self.work(await self.say(gold_thread, ask))
        assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        read = json.loads(
            next(
                m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j6-search"
            )
        )
        assert "Analyst" in json.dumps(read, ensure_ascii=False), read
        order = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j6-order")
        )
        assert order.get("ok") is False, order  # A tool that can trade is never trusted.
        assert seen.count("tools/call") == 1
        assert await self.pending(gold_thread, "trust_source") == []  # Remembered: no card.
        report = await self.request("GET", "/capabilities")
        trusted = [
            item
            for item in report["trusted_sources"]
            if item["kind"] == "mcp_server" and item["active"]
        ]
        assert len(trusted) >= 2, trusted  # X and the notes server, each once.
        # One owner step: connecting a new server (one secure card). Trusting it is the
        # owner's own words, no card (VISION 10.3.2).
        self.journey(name, 1)

    # Journey 5 -----------------------------------------------------------------------

    async def agent_adds_a_skill(self, news_id: str) -> None:
        """The news agent installs a pinned skill from a trusted source (github.com) and
        activates it itself; Capabilities shows it with Undo."""
        name = "J5 an agent adds a skill it needs"
        news_thread = await self.conversation(news_id)
        words = "تعلّم طريقة لتلخيص بيانات التضخم"
        repository = "cpi-briefs-" + uuid4().hex[:8]
        request = {
            "repository_url": "https://github.com/Example/" + repository,
            "commit": "b" * 40,
            "source_path": "cpi-brief/SKILL.md",
            "version": "1.0.0",
            "adapted_content": SKILL,
            "review": SKILL_REVIEW,
            "expected_version": 0,
            "workspace_revision": 0,
        }
        fetched: list[str] = []

        async def fetch(url: str, commit: str) -> bytes:
            fetched.append(url)
            return skill_archive()

        self.model.script(
            words,
            lambda t: call("j5-import", "skill_package_import", request),
            lambda t: call(
                "j5-activate",
                "skill_package_control",
                {
                    "skill_id": "cpi-brief",
                    "expected_version": t.result("j5-import")["resource_version"],
                    "action": "activate",
                    "workspace_revision": t.result("j5-import")["workspace_revision"],
                },
            ),
            "ثبّتّ طريقة تلخيص بيانات التضخم وفعّلتها.",
        )
        with patch("lonora_agent.skills.lifecycle.fetch_package", fetch):
            run = await self.work(await self.say(news_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        activated = json.loads(
            next(
                m.content
                for m in transcript
                if m.role == "tool" and m.tool_call_id == "j5-activate"
            )
        )
        assert activated["enabled"] is True, activated
        assert fetched, fetched
        report = await self.request("GET", "/capabilities")
        skill = next(
            item
            for item in report["skills"]
            if item["skill_id"] == "cpi-brief" and item["agent_id"] == news_id
        )
        assert (
            skill["enabled"]
            and skill["can_undo"]
            and skill["repository"] == "Example/" + repository
        )
        assert await self.pending(news_thread, "trust_source") == []
        self.journey(name, 0)

    # Journey 8 -----------------------------------------------------------------------

    async def ask_what_gold_did(self) -> None:
        """«ماذا فعل وكيل الذهب اليوم، ولماذا لم يدخل في افتتاح لندن؟»: Lonora reads the gold
        agent's own records on demand under its visible supervision grant."""
        name = "J8 ask Lonora what the gold agent did today"
        gold_id = self.created[0]
        gold_thread = await self.conversation(gold_id)
        summary = "London open: spread 4.1 above my 2.5 limit, no entry."
        london = "London open check"
        self.model.script(
            london,
            lambda t: call(
                "j8-wait",
                "market_decision_record",
                {
                    "account_id": self.account,
                    "symbol": GOLD,
                    "timeframe": "15m",
                    "action": "WAIT",
                    "summary": summary,
                },
            ),
            "لا دخول عند افتتاح لندن: السبريد واسع.",
        )
        from lonora_contracts.runs import RunRequest
        from lonora_db.runs import create_run

        async with self.db.sessions() as session, session.begin():
            wake = await create_run(
                session,
                self.owner,
                RunRequest(
                    thread_id=gold_thread, agent_id=gold_id, trigger="routine", prompt=london
                ),
            )
            wake_id = wake.id
        assert (await self.work(wake_id)).status == "completed"
        recorded = json.loads(
            next(
                m.content
                for m in self.model.sent[-1]
                if m.role == "tool" and m.tool_call_id == "j8-wait"
            )
        )
        assert recorded.get("ok") is not False, recorded
        words = "ماذا فعل وكيل الذهب اليوم، ولماذا لم يدخل في افتتاح لندن؟"
        first = len(self.model.sent)
        self.model.script(
            words,
            lambda t: calls(
                ("j8-look", "agent_inspect", {"agent_id": gold_id}),
                ("j8-why", "agent_inspect", {"agent_id": gold_id, "section": "decisions"}),
            ),
            "اشترى الذهب مرتين اليوم ضمن تفويضه، ولم يدخل عند افتتاح لندن لأن السبريد كان أوسع من حده.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        asked = "\n".join(m.content for m in self.model.sent[first])
        assert summary not in asked  # Read on demand, never injected.
        transcript = self.model.sent[-1]
        overview = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j8-look")
        )
        assert overview["ok"] is True and overview["authority"] == "supervised_read", overview
        decisions = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j8-why")
        )
        assert any(item["summary"] == summary for item in decisions["decisions"]), decisions
        self.journey(name, 0)

    # Journey 9 -----------------------------------------------------------------------

    async def preferences_for_every_agent(self) -> None:
        """«ردودك قصيرة بالعربي، وراسلني بدل ما تتصل» told to the gold agent: one owner
        profile and one reach-me preference that every agent reads from its next run."""
        name = "J9 tell one agent how to reply and reach me; every agent follows"
        gold_id = self.created[0]
        gold_thread = await self.conversation(gold_id)
        words = "ردودك قصيرة بالعربي، وراسلني بدل ما تتصل"
        preference = "- ردود قصيرة بالعربية."
        self.model.script(
            words,
            lambda t: calls(
                (
                    "j9-reach",
                    "owner_preferences_update",
                    {"reach_me": "message", "reply_language": "ar"},
                ),
                ("j9-read", "memory_read", {}),
            ),
            lambda t: call(
                "j9-profile",
                "memory_write",
                {
                    "version": t.result("j9-read")["version"],
                    "profile_version": t.result("j9-read")["owner_profile"]["profile_version"],
                    "operations": [{"action": "add", "section": "USER.md", "content": preference}],
                },
            ),
            "حاضر: ردود قصيرة بالعربية، وسأراسلك بدل الاتصال.",
        )
        run = await self.work(await self.say(gold_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        written = json.loads(
            next(
                m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j9-profile"
            )
        )
        assert written.get("ok") is not False, written
        profile = await self.request("GET", "/owner/profile")
        assert preference in profile["content"], profile
        revisions = cast(
            list[dict[str, Any]], await self.request("GET", "/owner/profile/revisions")
        )
        profile_change = next(item for item in revisions if item["document"] == "owner_profile")
        # Attributed to the agent that heard it and to the owner's message; revertible.
        assert profile_change["author_agent_id"] == gold_id, profile_change
        assert profile_change["from_owner_message"] is True, profile_change
        # Lonora's next run reads the same profile; nothing had to be repeated to it.
        first = len(self.model.sent)
        run = await self.work(await self.say(self.lonora_thread, "كيف حال السوق؟"))
        assert run.status == "completed"
        context = "\n".join(m.content for m in self.model.sent[first])
        assert "ردود قصيرة بالعربية" in context
        # Reach me: one preference for every agent, set from the gold agent's conversation.
        shared = await self.request("GET", "/owner/profile")
        assert shared["reach_me"]["channel"] == "message", shared["reach_me"]
        assert shared["reply_language"] == "ar", shared
        self.journey(name, 0)

    # Journey 13 ----------------------------------------------------------------------

    async def supervise_two_trading_agents(self, desk_id: str) -> None:
        """«خلي وكيل المراقبة يشرف على وكيل الذهب ووكيل الفضة»: the grants come from the
        owner's message with an Undo card; the supervisor reads them and never trades."""
        name = "J13 make an agent supervise two trading agents"
        gold_id = self.created[0]
        self.model.script(
            "أنشئ وكيل فضة",
            lambda t: call(
                "j13-silver",
                "agent_create",
                {
                    "template": "trading",
                    "name": "Silver agent",
                    "market": "XAGUSD",
                    "account_id": self.account,
                },
            ),
            "أنشأت وكيل الفضة على XAGUSD، ويسألك قبل كل صفقة.",
        )
        assert (
            await self.work(await self.say(self.lonora_thread, "أنشئ وكيل فضة"))
        ).status == "completed"
        async with self.db.sessions() as session:
            silver = await session.scalar(
                select(AgentRow).where(
                    AgentRow.owner_id == self.owner, AgentRow.name.like("Silver agent%")
                )
            )
        assert silver is not None
        self.created.append(silver.id)
        words = "خلي وكيل المراقبة يشرف على وكيل الذهب ووكيل الفضة"
        self.model.script(
            words,
            lambda t: call(
                "j13-supervise",
                "supervision_change",
                {
                    "action": "grant",
                    "supervisor_id": desk_id,
                    "supervised_ids": [gold_id, silver.id],
                },
            ),
            "صار وكيل المراقبة يشرف على وكيل الذهب ووكيل الفضة.",
        )
        run = await self.work(await self.say(self.lonora_thread, words))
        assert run.status == "completed", (run.status, run.error_code)
        async with self.db.sessions() as session:
            grants = list(
                await session.scalars(
                    select(SupervisionGrantRow).where(
                        SupervisionGrantRow.supervisor_agent_id == desk_id,
                        SupervisionGrantRow.supervised_agent_id.in_([gold_id, silver.id]),
                        SupervisionGrantRow.revoked_at.is_(None),
                    )
                )
            )
        assert sorted(g.supervised_agent_id for g in grants) == sorted([gold_id, silver.id]), grants
        undo = [
            c
            for c in await self.cards(self.lonora_thread)
            if c["kind"] == "supervision_created" and c["status"] == "pending"
        ]
        assert undo, "a supervision card with Undo"
        # The supervisor reads the silver agent's work and cannot trade for it.
        desk_thread = await self.conversation(desk_id)
        check = "راجع عمل وكيل الفضة"
        self.model.script(
            check,
            lambda t: call("j13-read", "agent_inspect", {"agent_id": silver.id}),
            lambda t: call(
                "j13-trade",
                "trade_execute",
                {
                    "action": "buy",
                    "account_id": self.account,
                    "symbol": SILVER,
                    "volume": "0.1",
                    "stop_loss": "23",
                },
            ),
            "قرأت عمل وكيل الفضة؛ لا أتداول عنه.",
        )
        before = await self.positions(self.account)
        run = await self.work(await self.say(desk_thread, check))
        assert run.status == "completed", (run.status, run.error_code)
        transcript = self.model.sent[-1]
        read = json.loads(
            next(m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j13-read")
        )
        assert read["ok"] is True, read
        traded = json.loads(
            next(
                m.content for m in transcript if m.role == "tool" and m.tool_call_id == "j13-trade"
            )
        )
        assert traded.get("ok") is False and traded.get("reason") == "agent analysis only", traded
        assert await self.positions(self.account) == before
        self.journey(name, 0)

    # Properties across every journey ---------------------------------------------------

    async def properties(self) -> None:
        import re

        # 1. Nothing traded without a grant or a tap: every live operation an agent sent
        #    was authorized by a signed grant or by the owner's approval of that operation.
        async with self.db.sessions() as session:
            rows = list(
                await session.scalars(
                    select(TradingJournalRow).where(
                        TradingJournalRow.owner_id == self.owner,
                        TradingJournalRow.account_id.in_([self.account, self.second_account]),
                        TradingJournalRow.status.not_in(["failed"]),
                    )
                )
            )
        assert rows
        async with self.db.sessions() as session:
            approved = {
                item["operation_id"]
                for approval in await session.scalars(
                    select(TradeApprovalRow).where(
                        TradeApprovalRow.owner_id == self.owner,
                        TradeApprovalRow.status.in_(["approved", "completed"]),
                    )
                )
                for item in approval.requests
            }
        granted = tapped = 0
        for row in rows:
            execution = cast(dict[str, Any], row.result.get("details", {}).get("execution") or {})
            assert execution.get("send_authorized") is True, row.operation_id
            if execution.get("account_authority_id"):
                granted += 1
            else:
                # Sent without a grant: only ever the owner's approval of this operation.
                assert row.operation_id in approved, (row.operation_id, row.status)
                tapped += 1
        assert granted and tapped, (granted, tapped)
        print(
            f"PASS nothing traded without a grant or a tap: {granted} operations under a signed "
            f"grant, {tapped} after the owner's approval"
        )

        # 2. No duplicates: one agent per name, one live watch per condition, one pending
        #    card per effect.
        async with self.db.sessions() as session:
            names = list(
                await session.scalars(select(AgentRow.name).where(AgentRow.id.in_(self.created)))
            )
            assert len(names) == len(set(names)) == len(set(self.created)), names
            watches = list(
                await session.scalars(
                    select(MarketWatchRow).where(
                        MarketWatchRow.owner_id == self.owner,
                        MarketWatchRow.payload["enabled"].as_boolean().is_(True),
                    )
                )
            )
            specs = [(w.agent_id, json.dumps(w.payload, sort_keys=True)) for w in watches]
            assert len(specs) == len(set(specs)), specs
            pending = list(
                await session.scalars(
                    select(OwnerActionRow).where(
                        OwnerActionRow.owner_id == self.owner, OwnerActionRow.status == "pending"
                    )
                )
            )
            effects = [(c.agent_id, c.kind, json.dumps(c.payload, sort_keys=True)) for c in pending]
            assert len(effects) == len(set(effects)), effects
        print(
            "PASS no operation, agent, watch or card was duplicated, across three worker restarts"
        )

        # 4. No credential value in any message, event, card, Run, attention item, approval,
        #    journal row, memory or anything the model was sent.
        from lonora_db.schema import MemoryRow, OwnerProfileRow

        async with self.db.sessions() as session:
            for model in (
                MessageRow,
                EventRow,
                OwnerActionRow,
                RunRow,
                AttentionRow,
                TradeApprovalRow,
                TradingJournalRow,
                MemoryRow,
                OwnerProfileRow,
            ):
                for row in await session.scalars(select(model)):
                    dumped = json.dumps({k: str(v) for k, v in vars(row).items()})
                    for secret in SECRETS:
                        assert secret not in dumped, (model.__name__, secret[:12])
        for messages in self.model.sent:
            text = "\n".join(m.content for m in messages)
            for secret in SECRETS:
                assert secret not in text, "a credential reached the model"
        print(
            f"PASS no credential value in transcripts, events, cards or {len(self.model.sent)} model requests"
        )

        # Normal views: the lines the server wrote into conversations carry no raw ids,
        # tool names or JSON.
        identifier = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        async with self.db.sessions() as session:
            lines = list(
                await session.scalars(
                    select(MessageRow.content)
                    .join(RunRow, RunRow.thread_id == MessageRow.thread_id, isouter=True)
                    .where(MessageRow.role == "assistant")
                    .distinct()
                )
            )
        # A colleague's result is stored inside its machine wrapper; Web and Mobile show
        # only the result (``peerOutcome`` in @lonora/core), so the check reads it so too.
        wrapper = re.compile(r"^<peer_outcome\b[^>]*>\n([\s\S]*)\n</peer_outcome>$")
        for stored in lines:
            matched = wrapper.match(stored)
            line = matched.group(1) if matched else stored
            assert not identifier.search(line) and '{"' not in line, line
        print(f"PASS {len(lines)} conversation lines carry no raw ids or JSON")


async def main() -> None:
    fixture = await Fixture().open()
    acceptance = Acceptance(fixture)
    try:
        await acceptance.setup()
        await acceptance.gold_agent_trades_on_its_own()
        await acceptance.approve_one_trade()
        watch = await acceptance.watch_london_session()
        await acceptance.pause_today_then_resume(watch)
        await acceptance.stop_watching(watch)
        await acceptance.lonora_manages_all_pairs()
        await acceptance.pause_every_account()
        await acceptance.resolve_uncertain_trade()
        news, desk, _ = await acceptance.news_agent_and_supervisor()
        await acceptance.add_mcp_server()
        await acceptance.agent_adds_a_skill(news)
        await acceptance.ask_what_gold_did()
        await acceptance.preferences_for_every_agent()
        await acceptance.supervise_two_trading_agents(desk)
        await acceptance.properties()
        for name, taken, expected in acceptance.results:
            print(f"  {name}: {taken}/{expected}")
        if acceptance.model.unscripted:
            print("unscripted triggers:", *acceptance.model.unscripted, sep="\n  ", file=sys.stderr)
    finally:
        async with acceptance.db.sessions() as session, session.begin():
            for row in await session.scalars(
                select(AgentRow).where(AgentRow.id.in_(acceptance.set_aside))
            ):
                row.paused = False
        await fixture.close(cleanup=False)


# --- The Web and Mobile acceptance specs (tests/{web,mobile}/simple-lonora.spec.mjs) ------

# The owner's sentences the browser specs type into the real composer.
UI_WORDS = {
    "create_gold": "أنشئ وكيل ذهب يدير صفقاتي على حسابي بنفسه، وخسارة يومية قصوى 2%",
    "pause_today": "أوقف فتح صفقات جديدة اليوم، وكمّل مراقبة الذهب",
    "buy_once": "اشترِ 0.1 ذهب على حسابي بوقف خسارة 150",
}


async def ui_turn(data: dict[str, Any]) -> dict[str, Any]:
    """A gateway worker for the browser specs: execute the owner's queued turn in one
    conversation with the scripted model, then the attention step (cards raised with no
    model). The specs send the owner's Arabic words through the real composer and tap the
    cards themselves; this only stands in for the worker process."""
    fixture = await Fixture().open()
    acceptance = Acceptance(fixture)
    try:
        await acceptance.provider()
        account, symbol = cast(str, data["account"]), cast(str, data["symbol"])
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        end_of_day = datetime.combine(
            datetime.now(ZoneInfo("UTC")).date(), time(23, 59, 59), ZoneInfo("UTC")
        ).isoformat()
        model = acceptance.model
        model.script(
            UI_WORDS["create_gold"],
            lambda t: call(
                "ui-create",
                "agent_create",
                {
                    "template": "trading",
                    "name": data.get("name", "Gold agent"),
                    "market": symbol,
                    "account_id": account,
                    "responsibility": "يدير صفقات الذهب على حساب المالك بنفسه.",
                },
            ),
            lambda t: call(
                "ui-grant",
                "owner_action_propose",
                {
                    "kind": "grant_authority",
                    "agent_id": t.result("ui-create")["agent"]["id"],
                    "daily_loss_percent": "2",
                },
            ),
            "أنشأت وكيل الذهب؛ وقّع البطاقة ليتداول بنفسه.",
        )
        model.script(
            UI_WORDS["pause_today"],
            lambda t: call(
                "ui-pause",
                "trade_restriction_create",
                {
                    "account_id": account,
                    "all_symbols": True,
                    "all_agents": True,
                    "action_class": "no_new_entries",
                    "valid_until": end_of_day,
                    "reason": "The owner asked: no new trades today; keep watching gold.",
                },
            ),
            "أوقفت الصفقات الجديدة لكل الوكلاء حتى نهاية اليوم، والمراقبة مستمرة.",
        )
        model.script(
            UI_WORDS["buy_once"],
            lambda t: call(
                "ui-buy",
                "trade_execute",
                {
                    "action": "buy",
                    "account_id": account,
                    "symbol": symbol,
                    "volume": "0.1",
                    "stop_loss": "150",
                },
            ),
            "نُفّذ الشراء بعد موافقتك.",
        )
        # Fresh quotes, as the broker stream keeps them.
        async with acceptance.db.sessions() as session, session.begin():
            book = await session.get(TradingAccountRow, account, with_for_update=True)
            assert book is not None
            quotes = dict(book.payload.get("quotes", {}))
            for name, value in quotes.items():
                quotes[name] = {**value, "observed_at": utcnow().isoformat()}
            book.payload = {**book.payload, "quotes": quotes}
            run = await session.scalar(
                select(RunRow)
                .where(RunRow.thread_id == data["thread"], RunRow.status == "queued")
                .order_by(RunRow.created_at.desc())
                .limit(1)
            )
            run_id = run.id if run else None
        status = error_code = None
        started = utcnow()
        if run_id:
            done = await acceptance.work(run_id)
            status, error_code = done.status, done.error_code
        await acceptance.project()
        created = None
        async with acceptance.db.sessions() as session:
            if data.get("name"):
                created = await session.scalar(
                    select(AgentRow.id).where(
                        AgentRow.owner_id == fixture.owner, AgentRow.name == data["name"]
                    )
                )
            # What this turn raised, so the spec taps exactly those cards.
            raised = [
                {"id": row.id, "kind": row.kind}
                for row in await session.scalars(
                    select(OwnerActionRow)
                    .where(
                        OwnerActionRow.thread_id == data["thread"],
                        OwnerActionRow.created_at >= started,
                    )
                    .order_by(OwnerActionRow.created_at)
                )
            ]
            restrictions = list(
                await session.scalars(
                    select(TradingRestrictionRow.id).where(
                        TradingRestrictionRow.account_id == account,
                        TradingRestrictionRow.source_run_id == run_id,
                    )
                )
            )
        return {
            "run": run_id,
            "status": status,
            "error_code": error_code,
            "agent": created,
            "cards": raised,
            "restrictions": restrictions,
        }
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    if sys.argv[1:] == ["--ui-turn"]:
        print(json.dumps(asyncio.run(ui_turn(json.load(sys.stdin)))))
    else:
        asyncio.run(main())
