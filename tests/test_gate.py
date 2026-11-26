"""The one gate, scripts/gate.sh: it runs every core test of VISION 14.1.2, and CI runs it."""

import ast
import re
import shlex
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from lonora_security.secrets import SecretCipher

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/gate.sh"
CI = ROOT / ".github/workflows/ci.yml"
# The gate's two commands that run the core tests: the whole suite, and the check scripts.
PYTEST = ["$PY", "-m", "pytest", "-q", "tests"]
FOUNDATION = ["$PY", "tests/run_foundation_checks.py", "--isolated-databases"]


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


def test_the_gate_runs_every_core_test_of_14_1_2() -> None:
    names = core_tests()
    assert len(names) == 11, names
    assert gate_gaps(GATE.read_text(encoding="utf-8")) == []
    checks = foundation_checks()
    for name in names:
        assert (ROOT / "tests" / name).is_file(), name
        assert name.startswith("test_") or name in checks, f"the gate does not run {name}"


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
    ],
)
def test_a_gate_that_drops_a_core_test_is_caught(line: str, mutated: str) -> None:
    gate = GATE.read_text(encoding="utf-8")
    assert gate.count(line) == 1
    assert gate_gaps(gate.replace(line, mutated))


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
