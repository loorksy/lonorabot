"""Owner amendment 1: Lonora has no Stop control, and nothing brings one back.

Every tracked file that ships or teaches the system (code, prompts, skills, tool
descriptions, catalogs, docs, scripts, deployment files) is free of the Stop control's
names and its owner-visible words. Migrations (which remove the stored records), the
mandate itself, tests (which assert absence) and recorded transcripts are history, not
the system, and are left out.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The Stop control's names in code and data.
NAMES = re.compile(
    r"emergency_stop|\bTradingControls?\b|trading_control|require_trading|resume_trading"
    r"|resumeTrading|stopNewTrading|global_trading|GlobalTrading|tradingBrake"
    r"|trading/controls|controls_updated|trading_not_started|start_trading_card"
)
# Its owner-visible and model-visible words, in English and Arabic, matched on the
# text with its whitespace collapsed.
WORDS = re.compile(
    r"stop new trading|resume trading|start trading|emergency stop"
    r"|إيقاف التداول|استئناف التداول|بدء التداول|التداول متوقف|التداول الجديد متوقف",
    re.IGNORECASE,
)
EXCLUDED = (
    "VISION.md",
    "packages/db/migrations/",
    "tests/",
    "apps/web/public/",
    "docs/ui-reference/",
    "pnpm-lock.yaml",
)


def shipped_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [ROOT / name for name in listed if not name.startswith(EXCLUDED)]


def test_no_shipped_file_names_or_shows_a_stop_control() -> None:
    found: list[str] = []
    for path in shipped_files():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        name = path.relative_to(ROOT)
        for number, line in enumerate(text.splitlines(), 1):
            if NAMES.search(line):
                found.append(f"{name}:{number}: {line.strip()[:120]}")
        # Words are matched across line wraps (prose and catalogs wrap mid-phrase).
        # Obsolete catalog entries never reach a screen, but none is kept either.
        for match in WORDS.finditer(" ".join(text.split())):
            found.append(f"{name}: {match.group(0)!r}")
    assert not found, "Stop control leftovers:\n" + "\n".join(found)


def test_the_scan_covers_the_shipped_tree() -> None:
    names = {str(path.relative_to(ROOT)) for path in shipped_files()}
    for expected in (
        "packages/agent-runtime/resources/system/lonora.md",
        "packages/trading/src/lonora_trading/execution.py",
        "apps/web/src/i18n/locales/ar/messages.po",
        "apps/mobile/lib/i18n.ts",
        "infra/compose/lonora-controls.sh",
    ):
        assert expected in names
    assert not any(name.startswith("packages/db/migrations/") for name in names)
