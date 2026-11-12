"""The acceptance scenario bank and the state each scenario starts from.

Every problem message of the owner's conversation of 2026-11-11 is one scenario in
tests/fixtures/agent_eval/scenarios.json: the owner's words exactly as he wrote them, the
state before them (signed full mandate, open position, existing watches, a waiting task,
earlier turns, broker faults) and the expected outcome. ``load`` reads the bank for one
account naming; ``seed`` and ``prepare`` build that state in a disposable database with the
fake MetaApi terminal of broker.py. Nothing here reaches a broker or carries a credential.
"""

import importlib
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from lonora_contracts.domain import AgentCreate, ThreadCreate
from lonora_db.agents import create_agent
from lonora_db.market_watches import MarketWatchRepository
from lonora_db.schema import (
    MarketWatchRow,
    MessageRow,
    RunRow,
    SettingRow,
    ThreadRow,
    TicketRow,
)
from lonora_db.tasks import finish_task, request_task_attention
from lonora_db.threads import create_thread
from sqlalchemy import delete, select

from . import broker

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/agent_eval"
SCENARIOS = FIXTURES / "scenarios.json"
CONVERSATION = FIXTURES / "conversation.json"
ACCOUNT = "agent-eval-demo"
# The owner of the conversation: Arabic profile, no reply language chosen (as on production).
PROFILE = "الاسم: المالك\nأتداول الذهب واليورو دولار على حساب Exness تجريبي."
ALL_ACTIONS = [
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
    "modify_position",
    "cancel_order",
    "modify_order",
]


def named(value: Any, variant: broker.Variant) -> Any:
    """``$XAUUSD`` anywhere in a scenario is the account's own name for that market."""
    if isinstance(value, dict):
        return {k: named(v, variant) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [named(item, variant) for item in cast(list[Any], value)]
    if isinstance(value, str):
        for base in broker.MARKETS:
            value = value.replace("$" + base, broker.broker_symbol(base, variant))
    return value


def conversation() -> dict[int, dict[str, Any]]:
    """The owner's conversation of 2026-11-11 by message number."""
    return {turn["n"]: turn for turn in json.loads(CONVERSATION.read_text())}


def load(path: Path = SCENARIOS) -> dict[str, dict[str, Any]]:
    """The bank by scenario id, ready to run and to score.

    A scenario that names a ``turn`` takes the owner's message from the conversation and
    every earlier turn as its history. Named states are merged in order, named checks are
    expanded, and every market is named as the scenario's account names it.
    """
    source = json.loads(path.read_text())
    turns = conversation()
    scenarios: dict[str, dict[str, Any]] = {}
    for item in source["scenarios"]:
        state: dict[str, Any] = {}
        for part in item["state"]:
            state.update(source["states"][part] if isinstance(part, str) else part)
        expect: list[dict[str, Any]] = []
        for check in item["expect"]:
            expect.extend(source["checks"][check] if isinstance(check, str) else [check])
        last = item.get("turn", item.get("history_until", 0) + 1)
        state["history"] = [
            {"role": turn["role"], "content": turn["content"]}
            for number, turn in turns.items()
            if number < last and turn["role"] in {"user", "assistant"}
        ]
        message = item.get("voice", {}).get("heard") or item.get("message")
        scenario = named({**item, "state": state, "expect": expect}, item.get("variant", "m"))
        scenarios[item["id"]] = {**scenario, "message": message or turns[item["turn"]]["content"]}
    return scenarios


def terminal(scenario: dict[str, Any]) -> broker.FakeTerminal:
    """The scenario's demo account before the owner's message."""
    state = scenario["state"]
    fake = broker.FakeTerminal(
        account_id=ACCOUNT, variant=scenario.get("variant", "m"), balance=Decimal("13944.57")
    )
    for base, bid in state.get("bids", {}).items():
        fake.bids[broker.broker_symbol(base, fake.variant)] = Decimal(bid)
    for position in state.get("positions", []):
        fake.open_position(**position)
    return fake


def arm(fake: broker.FakeTerminal, scenario: dict[str, Any], *, probe: bool = False) -> None:
    """The scenario's broker faults, counted from the owner's message on (a probe has no
    loop to retry in, so it states its own)."""
    state = scenario["probe"].get("state", {}) if probe else scenario["state"]
    for fault in state.get("faults", []):
        fake.fail(fault["kind"], after=fault.get("after", 0), times=fault.get("times", 1))


async def seed(api: Any, model: str) -> dict[str, str]:
    """The template database: the owner, his model, the demo account and a signed full mandate.

    ``api`` is genui_eval's in-process ``Api`` on a migrated disposable database, called
    inside ``broker.installed`` with LONORA_UI_TEST_PASSWORD set to the owner's password
    (the scripted authenticator enrolls with it).
    """
    sys.path.insert(0, str(ROOT / "tests"))
    # The scripted test authenticator of the test suite signs the mandate.
    device_type: Any = importlib.import_module("device_fixture").Device

    provider, name = model.split("/", 1)
    await api.request("PUT", f"/providers/{provider}/credential", {"api_key": "proxy-injected"})
    await api.request(
        "PUT",
        "/settings/models",
        {"mode": "unified", "unified": {"provider": provider, "model": name}},
    )
    profile = await api.request("GET", "/owner/profile")
    await api.request("PUT", "/owner/profile", {"content": PROFILE, "version": profile["version"]})
    account = await api.request(
        "POST",
        "/trading/connections",
        {
            "provider": "metaapi",
            "account_id": ACCOUNT,
            "api_key": "agent-eval-no-key",
            "enabled": True,
        },
    )
    lonora = next(a for a in await api.request("GET", "/agents") if a["role"] == "personal")
    thread = await api.request("POST", f"/agents/{lonora['id']}/conversation", {})
    device = await device_type.enroll(api)
    proposal = await api.request(
        "POST",
        f"/agents/{lonora['id']}/account-authorities",
        {
            "thread_id": thread["id"],
            "account_id": account["id"],
            "management_mode": "full",
            "symbol_scope": "account",
            "symbols": [],
            "actions": ALL_ACTIONS,
            "valid_until": None,
            "allow_manual_positions": True,
        },
    )
    grant = await device.sign_grant(api, proposal)
    return {
        "account_id": account["id"],
        "lonora_id": lonora["id"],
        "thread_id": thread["id"],
        "grant_id": grant["id"],
    }


async def prepare(api: Any, ids: dict[str, str], scenario: dict[str, Any]) -> dict[str, str]:
    """One scenario's own state on its copy of the template: mandate, model routing, the
    account Task, watches and earlier turns.

    Returns what a probe may name: ``$task``, ``$task_version`` and ``$watch0``, ``$watch1``
    ... in the scenario's order.
    """
    state = scenario["state"]
    if state.get("mandate", "full") == "none":
        await api.request("POST", f"/account-authorities/{ids['grant_id']}/revoke", {})
    async with api.runtime.db.sessions() as session, session.begin():
        if state.get("model_routing") == "unset":
            # A fresh install: a provider credential is saved and no model was chosen.
            await session.execute(delete(SettingRow).where(SettingRow.key == "model_routing"))
        # The account-management Task the signed mandate started (production: «إدارة حساب
        # التداول»), with its own conversation.
        task = await session.scalar(
            select(TicketRow).where(TicketRow.owner_id == api.owner).with_for_update()
        )
        assert task is not None
        if state.get("task") == "waiting":
            run = await session.get(RunRow, task.payload["run_id"])
            assert run is not None
            await request_task_attention(session, run, "agent_eval_seed")
        elif state.get("task") == "cancelled":
            finish_task(session, task, "cancelled")
        threads = {
            "lonora": (ids["lonora_id"], ids["thread_id"]),
            "task": (ids["lonora_id"], task.thread_id),
        }
        names = {"$task": task.id, "$task_version": str(task.version)}
        for number, watch in enumerate(state.get("watches", [])):
            if watch["owner"] == "other" and "other" not in threads:
                other = await create_agent(
                    session,
                    api.owner,
                    AgentCreate(
                        name="وكيل اليورو",
                        template="trading",
                        trading_account_id=ids["account_id"],
                        trading_symbol=watch["symbol"],
                    ),
                )
                thread = await create_thread(session, api.owner, ThreadCreate(agent_id=other.id))
                threads["other"] = (other.id, thread.id)
            agent_id, thread_id = threads[watch["owner"]]
            row = await MarketWatchRepository().create(
                session,
                api.owner,
                {
                    "account_id": ids["account_id"],
                    **{k: v for k, v in watch.items() if k != "owner"},
                },
                agent_id=agent_id,
                thread_id=thread_id,
            )
            if watch["owner"] == "task":
                row.state = {**row.state, "task_id": task.id, "task_run_id": task.payload["run_id"]}
            names[f"$watch{number}"] = row.id
        thread = await session.get(ThreadRow, ids["thread_id"], with_for_update=True)
        assert thread is not None
        for turn in state["history"]:
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
    return names


async def state_after(api: Any, ids: dict[str, str], fake: broker.FakeTerminal) -> dict[str, Any]:
    """What exists after the turn: the account, every watch of the owner and every task."""
    async with api.runtime.db.sessions() as session:
        watches = [
            {
                **{k: v for k, v in row.payload.items() if v is not None},
                "owner": "lonora" if row.agent_id == ids["lonora_id"] else "other",
                "of_task": "task_id" in row.state,
                "code": row.state.get("code"),
            }
            for row in await session.scalars(
                select(MarketWatchRow)
                .where(MarketWatchRow.owner_id == api.owner)
                .order_by(MarketWatchRow.created_at)
            )
        ]
        tasks = [
            {"title": row.payload.get("title"), "status": row.state["task"].get("status")}
            for row in await session.scalars(
                select(TicketRow).where(TicketRow.owner_id == api.owner)
            )
            if row.state.get("task")
        ]
    return {**json.loads(json.dumps(fake.state(), default=str)), "watches": watches, "tasks": tasks}
