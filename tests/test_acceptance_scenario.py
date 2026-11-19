"""The section 16 acceptance scenario harness (scripts/agent_eval/acceptance.py).

The scenario file quotes section 16 to the letter, every step of it is covered, step 6 is
void by Amendment 1, and the offline run (scripted model turns, the real loop, tools and
adapter on the fake terminal) passes every step whose feature is on this commit. A step
whose feature is missing is pending, never approximated. The offline run needs a
disposable PostgreSQL database and is skipped without one.
"""

import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.agent_eval import acceptance  # noqa: E402

SCENARIO = acceptance.load()
STEPS = {step["id"]: step for step in SCENARIO["steps"]}


def section_16() -> str:
    text = (ROOT / "VISION.md").read_text()
    start = text.index("## 16. Acceptance scenario")
    return text[start : text.index("## 17.", start)]


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def test_every_clause_is_quoted_to_the_letter():
    section = flat(section_16())
    assert flat(SCENARIO["setup"]) in section
    for step in SCENARIO["steps"]:
        if "void" not in step:
            assert flat(step["clause"]) in section, step["id"]


def test_every_sentence_of_section_16_is_a_step():
    section = section_16()
    quoted = " ".join(flat(step.get("clause", "")) for step in SCENARIO["steps"])
    for line in section.splitlines():
        # A numbered step or bullet, without its bold title ("**Morning.**").
        body = flat(re.sub(r"^\s*(\d+\.|-)\s*(\*\*[^*]+\*\*)?\s*", "", line))
        if not body or body == "--" or line.startswith(("#", "**Setup.**", "6.")):
            continue
        assert body in quoted or body in flat(SCENARIO["setup"]), body


def test_step_6_is_void_by_amendment_1():
    vision = (ROOT / "VISION.md").read_text()
    assert "- step 6 of section 16." in vision
    assert set(STEPS["6"]) == {"id", "title", "void", "needs"}
    assert "Amendment 1" in STEPS["6"]["void"]


def test_every_step_names_its_feature_and_its_owner():
    for step in SCENARIO["steps"]:
        if "void" in step:
            continue
        assert step["feature"] and step["owners"], step["id"]
        for defect in step.get("defects", []):
            assert set(defect) == {"check", "owner", "defect"} and all(defect.values())
        partial = step.get("partial", {"note": "-", "until": []})
        assert {"note", "until"} <= set(partial) <= {"note", "demo_note", "until"}, step["id"]
        assert partial["note"], step["id"]
        for need in step["needs"] + partial["until"]:
            assert set(need) <= {"pending", "tool", "code"} and len(need) == 1, step["id"]


def test_a_stand_in_runner_is_superseded_when_its_feature_lands():
    step = {**STEPS["4c"], "partial": {"note": "n", "until": [{"tool": "trade_execute"}]}}
    rows = acceptance.status({"steps": [step]})
    assert rows[0]["state"] == "not written"


def test_a_step_with_a_runner_has_its_script_and_situation():
    for name in acceptance.RUNNERS:
        assert {"given", "script"} <= set(STEPS[name]), name


def test_a_missing_feature_keeps_its_step_pending():
    assert acceptance.missing([{"pending": "W-X: a feature"}]) == ["W-X: a feature"]
    assert acceptance.missing([{"tool": "no_such_tool"}]) == ["tool no_such_tool"]
    assert acceptance.missing([{"code": "lonora_trading.no_such_module:x"}]) == [
        "lonora_trading.no_such_module:x"
    ]
    assert acceptance.missing([{"tool": "trade_execute"}]) == []
    assert acceptance.missing([{"code": "lonora_trading.execution:ExecutionService"}]) == []
    rows = {row["step"]: row for row in acceptance.status(SCENARIO)}
    assert rows["6"]["state"] == "void"
    assert rows["7b"]["state"] == "pending"


@pytest.mark.asyncio
async def test_a_lost_reply_is_applied_at_the_broker_and_never_answered():
    terminal = acceptance.AcceptanceTerminal(account_id="accept-unit")
    position = terminal.open_position("XAUUSD", "buy", "0.02", "4031.500")
    terminal.lose_reply("close_position")
    with pytest.raises(ConnectionError):
        await terminal.close_position(position["id"])
    assert terminal.positions == [] and terminal.deals[-1]["positionId"] == position["id"]
    assert terminal.calls == ["close_position"]
    # The drop is one event: the next close answers.
    again = terminal.open_position("XAUUSD", "buy", "0.01", "4031.500")
    assert (await terminal.close_position(again["id"]))["stringCode"] == "TRADE_RETCODE_DONE"


def test_the_offline_run_passes_every_step_whose_feature_is_here():
    url = make_url(os.environ.get("LONORA_DATABASE_URL") or "sqlite://")
    if not url.drivername.startswith("postgresql"):
        pytest.skip("the offline run needs a disposable PostgreSQL (LONORA_DATABASE_URL)")
    own = url.set(database=f"accept_{uuid4().hex[:10]}_test")
    environment = {**os.environ, "LONORA_DATABASE_URL": own.render_as_string(hide_password=False)}
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts/agent_eval/acceptance.py"), "--offline", "--json"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert "[" in done.stdout, done.stderr[-2000:]
    report = json.loads(done.stdout[done.stdout.index("[") :])
    failed = {row["step"]: row for row in report if row["state"] == "fail"}
    assert not failed, json.dumps(failed, ensure_ascii=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert {row["step"] for row in report} == set(STEPS)
    ran = {row["step"]: row for row in report if row["state"] in {"pass", "known defect"}}
    assert {"1", "4a", "4c", "5", "7a"} <= set(ran)
    # Today's stand-ins are said, never passed off as the step itself.
    assert all("partial" in ran[step] for step in ("1", "4a", "5", "7a"))
    # The step's own actor: the gold agent in Full sent the close, no stand-in.
    assert "partial" not in ran["4c"]
    assert {row["check"]: row["ok"] for row in ran["4c"]["checks"]}[acceptance.GOLD_SENT]
    # A defect is held strictly: its step fails exactly the checks it names, and a fixed
    # defect (the step passes) must leave the scenario file in the same change.
    for row in report:
        named = STEPS[row["step"]].get("defects", [])
        if row["state"] in {"pass", "known defect"}:
            assert (row["state"] == "known defect") == bool(named), row["step"]
            failing = {check["check"] for check in row["checks"] if not check["ok"]}
            assert failing == {item["check"] for item in named}, row["step"]


def test_a_refusal_raised_or_answered_counts_against_authority():
    from lonora_agent.environment import classify, error_class

    raised = {"tool": "trade_execute", "error": "agent_analysis_only"}
    answered = {"tool": "trade_execute", "result": {"ok": False, "code": "approval_required"}}
    uncertain = {"tool": "trade_execute", "result": {"status": "ambiguous"}}
    assert [acceptance.refusal(call) for call in (raised, answered, uncertain)] == [
        "agent_analysis_only",
        "approval_required",
        None,
    ]
    for code in ("agent_analysis_only", "approval_required"):
        assert error_class(code, classify(code, None)["category"]) == "permission"


def test_the_demo_broker_runs_only_the_steps_that_may_reach_it():
    """--broker demo refuses a step it may not run before any value is asked for."""
    assert acceptance.DEMO_STEPS <= set(acceptance.RUNNERS)
    url = "postgresql+asyncpg://nobody@127.0.0.1:5432/accept_refused_test"
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/agent_eval/acceptance.py"),
            "--offline",
            "--broker",
            "demo",
            "--steps",
            "4c",
        ],
        env={**os.environ, "LONORA_DATABASE_URL": url},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        # No controlling terminal: a prompt would have to come through stdin/stderr.
        start_new_session=True,
        timeout=120,
    )
    assert done.returncode != 0
    assert "--broker demo runs only steps 1" in done.stderr
    assert "MetaApi demo" not in done.stdout + done.stderr


# --broker demo on W-BROKER's fakes in place of MetaApi: the step body fails after the
# account is connected, once with an error and once interrupted (Ctrl-C). Then the run is
# interrupted while MetaApi creates the account (it is created; the answer never reaches
# the product), and the last time interrupted again while the harness asks MetaApi what is
# left.
DEMO_FAILS = """
import asyncio, json, os
from datetime import timedelta
from unittest.mock import patch
from lonora_adapters.brokers.base import BrokerManager
from scripts.agent_eval import acceptance, broker

async def main():
    base = acceptance.harness.disposable(os.environ["LONORA_DATABASE_URL"])
    step = {item["id"]: item for item in acceptance.load()["steps"]}["1"]
    login, server = step["given"]["login"], step["given"]["server"]
    demo = {"login": login, "server": server, "password": "accept-demo-master",
            "token": "accept.demo.token"}
    api = broker.FakeProvisioningApi(servers={server: {login: demo["password"]}},
                                     prefix="accept-demo")
    terminals = [broker.FakeTerminal(account_id=f"accept-demo-{n:04d}", login=login,
                                     server=server) for n in (1, 2)]
    ids = await acceptance.runner.template(base, acceptance.runner.MODEL)
    client = lambda token: broker.FakeMetaApiProvisioning(api, token)
    rows, left, lookups = [], [], []
    try:
        with (
            broker.installed(*terminals),
            patch("lonora_trading.broker_provisioning.provisioning_client", client),
            patch.object(BrokerManager, "provisioning_factory", staticmethod(client), create=True),
            patch.object(acceptance, "DEMO_PASS_SECONDS", 0),
            # A harness that waited out an account nobody removes would ask again and again.
            patch.object(acceptance, "REMOVAL_WAIT", timedelta(seconds=5)),
        ):
            for failure in (TimeoutError("the wake's run did not end"),
                            asyncio.CancelledError()):
                async def fails(*_, failure=failure):
                    raise failure
                with patch.object(acceptance, "posted", fails):
                    rows.append(await acceptance.run_step(base, ids, step, False, demo))
            left.append(len(api.accounts))
            for again in (False, True):
                create = api.create_account
                listing = api.get_accounts_with_infinite_scroll_pagination
                interrupted = []
                async def creates(*args, **kwargs):
                    await create(*args, **kwargs)
                    interrupted.append(len(api.calls))
                    raise asyncio.CancelledError()
                async def lists(*args, again=again, **kwargs):
                    if interrupted and again:
                        raise asyncio.CancelledError()
                    return await listing(*args, **kwargs)
                with (
                    patch.object(api, "create_account", creates),
                    patch.object(api, "get_accounts_with_infinite_scroll_pagination", lists),
                ):
                    rows.append(await acceptance.run_step(base, ids, step, False, demo))
                lookups.append(api.calls[interrupted[0]:].count("list"))
                left.append(len(api.accounts))
                api.accounts.clear()  # removed at MetaApi by hand, as the row asks
    finally:
        await acceptance.harness.admin(
            base, f'DROP DATABASE IF EXISTS "{base.database}" WITH (FORCE)')
    print(json.dumps({"rows": rows, "creates": api.calls.count("create_account"),
                      "left": left, "lookups": lookups}))

asyncio.run(main())
"""


def test_the_demo_broker_says_what_metaapi_holds_when_the_step_fails():
    """A step that raises or is interrupted after the account is connected still removes
    it and reports what MetaApi holds, in its own row. One interrupted before it is
    connected says at once that the account is still there, even when interrupted again."""
    url = make_url(os.environ.get("LONORA_DATABASE_URL") or "sqlite://")
    if not url.drivername.startswith("postgresql"):
        pytest.skip("the demo run needs a disposable PostgreSQL (LONORA_DATABASE_URL)")
    own = url.set(database=f"accept_{uuid4().hex[:10]}_test")
    done = subprocess.run(
        [sys.executable, "-c", DEMO_FAILS],
        cwd=ROOT,
        env={**os.environ, "LONORA_DATABASE_URL": own.render_as_string(hide_password=False)},
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    outcome = json.loads(done.stdout.strip().splitlines()[-1])
    failed, interrupted, connecting, twice = outcome["rows"]
    assert failed["error"] == "TimeoutError: the wake's run did not end"
    for row in (interrupted, connecting, twice):
        assert row["error"] == "interrupted"
    for row in (failed, interrupted):
        assert row["state"] == "fail"
        # The step's own checks were never reached; MetaApi's row is there all the same.
        assert [(check["check"], check["ok"]) for check in row["checks"]] == [
            ("nothing is left at MetaApi", True)
        ], row
    # Each run created its account at the fake MetaApi. The two connected ones were removed;
    # the two whose connect was interrupted are still there, and their rows say so.
    assert outcome["creates"] == 4 and outcome["left"] == [0, 1, 1]
    seen = "an account for this login and server is still at MetaApi: remove it there"
    assert connecting["checks"] == [
        {"check": "nothing is left at MetaApi", "ok": False, "seen": seen}
    ]
    # Nobody asked MetaApi to remove it: it is reported at the first lookup, not waited for.
    assert outcome["lookups"][0] == 1
    # Interrupted again during that lookup: the row is there, and says so.
    assert twice["checks"] == [
        {
            "check": "nothing is left at MetaApi",
            "ok": False,
            "seen": "the cleanup did not finish: check the account there",
        }
    ]


class MetaApiAnswers:
    """MetaApi's answers to the harness's lookups for the demo login and server, in turn;
    the last answer repeats."""

    def __init__(self, *answers: str | None):
        self.answers, self.finds = list(answers), 0

    async def find(self, login: str, server: str) -> SimpleNamespace | None:
        assert (login, server) == ("50000077", "Exness-MT5Trial16")
        self.finds += 1
        state = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return SimpleNamespace(state=state) if state else None

    async def close(self) -> None:
        pass


async def left_at_metaapi(
    monkeypatch: pytest.MonkeyPatch, metaapi: MetaApiAnswers, existed: bool, wait: float
) -> tuple[str, bool, str]:
    async def no_connection(*_: object) -> dict[str, str]:
        return {}

    def client(token: str) -> MetaApiAnswers:
        assert token == "accept.demo.token"
        return metaapi

    monkeypatch.setattr(acceptance, "card_result", no_connection)
    monkeypatch.setattr(acceptance.broker_provisioning, "provisioning_client", client)
    monkeypatch.setattr(acceptance, "DEMO_PASS_SECONDS", 0.01)
    monkeypatch.setattr(acceptance, "REMOVAL_WAIT", timedelta(seconds=wait))
    demo = {"login": "50000077", "server": "Exness-MT5Trial16", "token": "accept.demo.token"}
    stage = SimpleNamespace(demo=demo)
    [row] = await acceptance.removed_demo(stage, "card", existed)  # type: ignore[arg-type]
    return row


@pytest.mark.asyncio
async def test_the_demo_cleanup_waits_for_metaapi_to_finish_a_removal(
    monkeypatch: pytest.MonkeyPatch,
):
    """MetaApi removes an account asynchronously: DELETING is not a leftover yet."""
    metaapi = MetaApiAnswers("DELETING", "DELETING", None)
    row = await left_at_metaapi(monkeypatch, metaapi, existed=False, wait=60)
    assert row == ("nothing is left at MetaApi", True, "no account for this login and server")
    assert metaapi.finds == 3


@pytest.mark.asyncio
async def test_the_demo_cleanup_reports_an_account_still_there_after_the_wait(
    monkeypatch: pytest.MonkeyPatch,
):
    metaapi = MetaApiAnswers("DELETING")
    name, ok, seen = await left_at_metaapi(monkeypatch, metaapi, existed=False, wait=0.05)
    assert (name, ok) == ("nothing is left at MetaApi", False)
    assert seen == "an account for this login and server is still at MetaApi: remove it there"
    assert metaapi.finds > 1


@pytest.mark.asyncio
async def test_the_demo_cleanup_reports_an_account_nobody_removes_at_once(
    monkeypatch: pytest.MonkeyPatch,
):
    """An account that is not being removed (its connect was interrupted, or its removal
    failed) will not go on its own: it is reported at the first lookup."""
    metaapi = MetaApiAnswers("DEPLOYING")
    name, ok, seen = await left_at_metaapi(monkeypatch, metaapi, existed=False, wait=60)
    assert (name, ok) == ("nothing is left at MetaApi", False)
    assert seen == "an account for this login and server is still at MetaApi: remove it there"
    assert metaapi.finds == 1


@pytest.mark.asyncio
async def test_the_demo_cleanup_keeps_an_account_that_was_there_before_the_run(
    monkeypatch: pytest.MonkeyPatch,
):
    """The product reuses an account already at MetaApi and never removes it: the run did
    not leave it, so it is neither a failure nor something to remove."""
    metaapi = MetaApiAnswers("DEPLOYED")
    row = await left_at_metaapi(monkeypatch, metaapi, existed=True, wait=60)
    assert row == (
        "nothing is left at MetaApi",
        True,
        "the account for this login and server was there before the run: kept",
    )
    assert metaapi.finds == 1


def test_a_balance_is_read_from_the_agents_words():
    assert acceptance.states("10000", "الرصيد 10,000 دولار")
    assert acceptance.states("10000", "الرصيد ١٠٠٠٠ دولار")
    assert acceptance.states("10123.45", "Balance 10,123.45 USD")
    assert acceptance.states("10000", "الرصيد ١٠٬٠٠٠ دولار")
    assert acceptance.states("1000000", "الرصيد 1 000 000 دولار")
    # A space between two numbers does not join them.
    assert acceptance.states("10000", "في 2026 10000 دولار")
    assert not acceptance.states("10000", "الرصيد 1000 دولار")
    assert not acceptance.states("10000", "رقم الحساب 100001")
    assert not acceptance.states("?", "?")
