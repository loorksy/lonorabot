"""The one gate, scripts/gate.sh: it runs the core tests of VISION 14.1.2 and 6.1-6.9 and the
offline acceptance run, leaves the checkout as it found it, and CI runs it."""

import ast
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, NamedTuple, cast

import pytest
import yaml
from lonora_security.secrets import SecretCipher

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/gate.sh"
CI = ROOT / ".github/workflows/ci.yml"
# The gate's two commands that run the core tests: the whole suite, and the check scripts.
PYTEST = ["$PY", "-m", "pytest", "-q", "tests"]
FOUNDATION = ["$PY", "tests/run_foundation_checks.py", "--isolated-databases"]
CATALOG = "apps/web/src/i18n/locales/ar/messages.po"
ACCEPTANCE = ROOT / "tests/test_acceptance_scenario.py"
OFFLINE_RUN = "test_the_offline_run_passes_every_step_whose_feature_is_here"
# The stubbed gate's database password: it must never reach a command line.
PASSWORD = "gate-only-password"


def core_tests() -> list[str]:
    """The files VISION 14.1.2 says MUST pass after every step."""
    vision = (ROOT / "VISION.md").read_text(encoding="utf-8")
    section = vision.split("2. **Core regression tests.**", 1)[1].split("3. **Assertions.**", 1)[0]
    return re.findall(r"^\s+- `tests/([a-z0-9_]+\.py)`$", section, re.M)


def gate_commands(gate: str, word: str) -> list[list[str]]:
    """The command lines of the gate text ``gate`` that name ``word``, split as the shell does."""
    return [
        shlex.split(line)
        for line in gate.splitlines()
        if word in line and not line.lstrip().startswith("#")
    ]


def foundation_checks() -> set[str]:
    """The check scripts run_foundation_checks.py runs, each on a fresh database."""
    tree = ast.parse((ROOT / "tests/run_foundation_checks.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == ["CHECKS"]:
            return set(cast(tuple[str, ...], ast.literal_eval(node.value)))
    raise AssertionError("tests/run_foundation_checks.py has no CHECKS")


def gate_gaps(gate: str) -> list[str]:
    """Why the gate text ``gate`` would not run every core test; empty when it runs them all.

    Each of its two core commands is pinned exactly: any option, prefix or ``|| true`` changes
    what runs. The full suite runs unfiltered, so every tests/test_*.py file is collected.
    """
    gaps: list[str] = []
    for word, expected in (("pytest", PYTEST), ("run_foundation_checks", FOUNDATION)):
        found = [command for command in gate_commands(gate, word) if command[0] != "step"]
        if found != [expected]:
            gaps.append(f"expected the one command {' '.join(expected)}, found {found}")
    return gaps


class Run(NamedTuple):
    code: int
    output: str
    calls: list[str]
    changed: str


def stubbed_run(tmp_path: Path, gate: str) -> Run:
    """Run the gate text ``gate`` in a scratch checkout where each tool it calls is a stub.

    Every stub records its name and arguments; the Python stub also answers the database
    helper and alembic, and the pnpm stub's extraction moves a line reference in the Arabic
    catalog, as Lingui does. ``changed`` lists the tracked files the run left modified.
    """
    tree, calls = tmp_path / "checkout", tmp_path / "calls"
    record = '#!/bin/sh\necho "$(basename "$0") $*" >> "$GATE_CALLS"\n'
    python = (
        '[ "$1" != - ] || cat > /dev/null\n'
        'case "$*" in *" create "*) echo postgresql://gate@localhost/fresh_test ;;'
        ' *" heads") echo "0001 (head)" ;; esac\n'
    )
    files = {
        "scripts/gate.sh": gate,
        "scripts/build.sh": record,
        "scripts/migrate.sh": record,
        ".venv/bin/python": record + python,
        "bin/pnpm": record + f'case "$*" in *" i18n") echo "#: moved.tsx:2" >> {CATALOG} ;; esac\n',
        CATALOG: 'msgid "Hello"\nmsgstr "مرحبا"\n',
    }
    for name, text in files.items():
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    calls.touch()
    for git in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *git], cwd=tree, check=True)
    environment = {
        **os.environ,
        "PATH": f"{tree / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "LONORA_DATABASE_URL": f"postgresql+asyncpg://gate:{PASSWORD}@localhost/gate",
        "GATE_CALLS": str(calls),
    }
    done = subprocess.run(
        ["bash", "scripts/gate.sh"],
        cwd=tree,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=60,
    )
    changed = subprocess.run(
        ["git", "diff", "--name-only"], cwd=tree, capture_output=True, text=True, check=True
    ).stdout
    return Run(
        done.returncode, done.stdout, calls.read_text(encoding="utf-8").splitlines(), changed
    )


def run_gaps(run: Run) -> list[str]:
    """Why a stubbed run of the gate did not run every core test; empty when it did."""
    # The Python stub records itself as "python", where the gate wrote "$PY".
    gaps = [
        f"never ran {' '.join(command)}"
        for command in (PYTEST, FOUNDATION)
        if " ".join(["python", *command[1:]]) not in run.calls
    ]
    if run.code != 0 or not run.output.rstrip().endswith("== gate passed"):
        gaps.append(f"stopped before its last step (exit {run.code}): {run.output[-1500:]}")
    return gaps


def test_the_gate_runs_every_core_test_of_14_1_2(tmp_path: Path) -> None:
    names = core_tests()
    assert len(names) == 11, names
    gate = GATE.read_text(encoding="utf-8")
    assert gate_gaps(gate) == []
    assert run_gaps(stubbed_run(tmp_path, gate)) == []
    checks = foundation_checks()
    for name in names:
        assert (ROOT / "tests" / name).is_file(), name
        assert name.startswith("test_") or name in checks, f"the gate does not run {name}"


def test_every_check_script_of_the_safety_core_runs_in_the_gate() -> None:
    # B0: the tests of 6.1-6.9 run on every change. A check script that cites one of those
    # clauses runs in the foundation checks; the full pytest already holds every test_*.py.
    checks = foundation_checks()
    cited = [
        path.name
        for path in sorted((ROOT / "tests").glob("check_*.py"))
        if re.search(r"(?<![\d.])6\.[1-9](?!\d)", path.read_text(encoding="utf-8"))
    ]
    assert cited
    assert [name for name in cited if name not in checks] == []


@pytest.mark.parametrize(
    ("line", "mutated"),
    [
        (
            '"$PY" -m pytest -q tests',
            '"$PY" -m pytest -q tests --ignore=tests/test_financial_admission.py',
        ),
        (
            '"$PY" -m pytest -q tests',
            '"$PY" -m pytest -q tests --deselect=tests/test_tool_execution_core.py',
        ),
        ('"$PY" -m pytest -q tests', '"$PY" -m pytest -q tests -knot_financial'),
        ('"$PY" -m pytest -q tests', '"$PY" -m pytest -q tests || true'),
        ('"$PY" tests/run_foundation_checks.py', ': "$PY" tests/run_foundation_checks.py'),
        ('step "full pytest"', 'exit 0\nstep "full pytest"'),
    ],
)
def test_a_gate_that_drops_a_core_test_is_caught(tmp_path: Path, line: str, mutated: str) -> None:
    gate = GATE.read_text(encoding="utf-8")
    assert gate.count(line) == 1
    gate = gate.replace(line, mutated)
    assert gate_gaps(gate) + run_gaps(stubbed_run(tmp_path, gate))


def acceptance_gaps(source: str) -> list[str]:
    """Why the full pytest would not run ``acceptance.py --offline`` (roadmap B0), given the text
    of tests/test_acceptance_scenario.py; empty when it would."""
    runs = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == OFFLINE_RUN
    ]
    if len(runs) != 1:
        return [f"tests/test_acceptance_scenario.py has no {OFFLINE_RUN}"]
    marks = [ast.unparse(decorator) for decorator in runs[0].decorator_list]
    gaps = [
        f"{OFFLINE_RUN} is marked {mark}" for mark in marks if "skip" in mark or "xfail" in mark
    ]
    if "pytestmark" in source:
        gaps.append("tests/test_acceptance_scenario.py marks every test")
    body = ast.get_source_segment(source, runs[0]) or ""
    if '"scripts/agent_eval/acceptance.py"' not in body or '"--offline"' not in body:
        gaps.append(f"{OFFLINE_RUN} does not run scripts/agent_eval/acceptance.py --offline")
    return gaps


@pytest.mark.parametrize(
    ("text", "mutated"),
    [
        (f"def {OFFLINE_RUN}", "def test_renamed"),
        (f"def {OFFLINE_RUN}", f'@pytest.mark.skip(reason="later")\ndef {OFFLINE_RUN}'),
        ('"--offline", ', ""),
    ],
)
def test_the_full_run_holds_the_offline_acceptance_run(text: str, mutated: str) -> None:
    # The gate has no step of its own for it: its full pytest runs it through this one test,
    # on the fresh PostgreSQL database the gate gives it.
    source = ACCEPTANCE.read_text(encoding="utf-8")
    assert acceptance_gaps(source) == []
    assert source.count(text) == 1
    assert acceptance_gaps(source.replace(text, mutated))


def test_the_gate_leaves_the_checkout_as_it_found_it(tmp_path: Path) -> None:
    # A signed gate result describes the commit: the catalogs Lingui extracts in place are
    # restored once they are counted.
    assert stubbed_run(tmp_path, GATE.read_text(encoding="utf-8")).changed == ""


def test_the_database_password_never_reaches_a_command_line(tmp_path: Path) -> None:
    # Other users of a shared build server can read every process's arguments.
    calls = stubbed_run(tmp_path, GATE.read_text(encoding="utf-8")).calls
    assert calls and not [call for call in calls if PASSWORD in call]


def test_ci_runs_the_gate_and_keeps_no_list_of_its_own() -> None:
    workflow = cast(dict[str, Any], yaml.safe_load(CI.read_text(encoding="utf-8")))
    steps = cast(list[dict[str, Any]], workflow["jobs"]["build"]["steps"])
    runs = [str(step["run"]).strip() for step in steps if "run" in step]
    assert runs[-1] == "bash scripts/gate.sh"
    for run in runs[:-1]:
        assert "tests/" not in run and "pytest" not in run and "pnpm test" not in run, run


def test_every_encryption_key_fixture_is_a_valid_fernet_key() -> None:
    fixtures = [
        key
        for source in (CI, GATE)
        for key in re.findall(
            r"LONORA_ENCRYPTION_KEY(?::\s+|=)['\"]?([A-Za-z0-9_=-]+)", source.read_text("utf-8")
        )
    ]
    assert fixtures
    for key in fixtures:
        SecretCipher(key)
