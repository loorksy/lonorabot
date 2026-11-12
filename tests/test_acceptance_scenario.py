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
from pathlib import Path
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
        assert set(partial) == {"note", "until"} and partial["note"], step["id"]
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
    assert {"4a", "4c", "5", "7a"} <= set(ran)
    # Today's stand-ins are said, never passed off as the step itself.
    assert all("partial" in ran[step] for step in ("4a", "5", "7a"))
    # The step's own actor: the gold agent in Full sent the close, no stand-in.
    assert ran["4c"]["state"] == "pass" and "partial" not in ran["4c"]
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
