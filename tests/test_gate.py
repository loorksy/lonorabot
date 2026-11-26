"""The one gate, scripts/gate.sh: it runs every core test of VISION 14.1.2, and CI runs it."""

import ast
import re
import shlex
from pathlib import Path
from typing import Any, cast

import yaml
from lonora_security.secrets import SecretCipher

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/gate.sh"
CI = ROOT / ".github/workflows/ci.yml"


def core_tests() -> list[str]:
    """The files VISION 14.1.2 says MUST pass after every step."""
    vision = (ROOT / "VISION.md").read_text(encoding="utf-8")
    section = vision.split("2. **Core regression tests.**", 1)[1].split("3. **Assertions.**", 1)[0]
    return re.findall(r"^\s+- `tests/([a-z0-9_]+\.py)`$", section, re.M)


def gate_commands(word: str) -> list[list[str]]:
    """The gate's command lines that name ``word``, split as the shell splits them."""
    lines = GATE.read_text(encoding="utf-8").splitlines()
    return [
        shlex.split(line) for line in lines if word in line and not line.lstrip().startswith("#")
    ]


def foundation_checks() -> set[str]:
    """The check scripts run_foundation_checks.py runs, each on a fresh database."""
    tree = ast.parse((ROOT / "tests/run_foundation_checks.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == ["CHECKS"]:
            return set(cast(tuple[str, ...], ast.literal_eval(node.value)))
    raise AssertionError("tests/run_foundation_checks.py has no CHECKS")


def test_the_gate_runs_every_core_test_of_14_1_2() -> None:
    names = core_tests()
    assert len(names) == 11, names
    pytest = [command for command in gate_commands("pytest") if "pytest" in command]
    assert len(pytest) == 1, pytest
    # The whole suite, unfiltered: every tests/test_*.py file is collected.
    arguments = pytest[0][pytest[0].index("pytest") + 1 :]
    assert [argument for argument in arguments if not argument.startswith("-")] == ["tests"]
    assert not {"-k", "--ignore", "--deselect", "--ignore-glob", "-m"} & set(arguments)
    assert any(
        "tests/run_foundation_checks.py" in command and "--isolated-databases" in command
        for command in gate_commands("run_foundation_checks")
    )
    checks = foundation_checks()
    for name in names:
        assert (ROOT / "tests" / name).is_file(), name
        assert name.startswith("test_") or name in checks, f"the gate does not run {name}"


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
