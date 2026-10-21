"""Check compact operating policy against the live tool routing metadata.

Tool schemas come from the runtime registry and are never copied into the manual.
Use --check in CI. This requires no network or database.
"""

import argparse
import hashlib
import json
from pathlib import Path

from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "packages/agent-runtime/resources/system/lonora.md"
MANIFEST = MANUAL.with_name("manifest.json")
EXAMPLES_SECTION = "## Behavioral examples"
TOOL_REFERENCE_MARKER = "<!-- tool-reference:generated -->"
MODULE_POLICY = {
    "agents": "collaboration",
    "message": "collaboration",
    "subagent": "collaboration",
    "collaboration": "collaboration",
    "memory": "memory",
    "scratchpad": "memory",
    "skills": "memory",
    "routine": "tasks",
    "tasks": "tasks",
    "runtime_control": "tasks",
    "search": "research",
    "mcp": "research",
    "artifacts": "files",
    "market": "market",
    "market_watch": "market",
    "trading_decision": "intelligence",
    "relationships": "intelligence",
    "opportunity": "intelligence",
    "shadow": "intelligence",
    "chart": "charts",
    "chart_state": "charts",
    "chart_indicator": "charts",
    "chart_snapshot": "charts",
    "account": "account",
    "trade": "trading",
    "trading_goal": "goals",
    "super_bot": "goals",
    "registry": "core",
}


def export() -> tuple[str, str]:
    registry = load_tools()
    text = (
        MANUAL.read_text().split(EXAMPLES_SECTION)[0].split(TOOL_REFERENCE_MARKER)[0].rstrip()
        + "\n"
    )
    mapping: dict[str, str] = {}
    for name, tool in registry.tools.items():
        module = tool.handler.__module__.rsplit(".", 1)[-1]
        mapping[name] = MODULE_POLICY[module]
    manifest = (
        json.dumps(
            {
                "version": 2,
                "manual_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "bootstrap_sha256": {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((MANUAL.parent.parent / "bootstrap").glob("*.md"))
                },
                "tool_policies": mapping,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return text, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text, manifest = export()
    if args.check:
        if MANUAL.read_text() != text or not MANIFEST.is_file() or MANIFEST.read_text() != manifest:
            raise SystemExit(
                "Agent policy routing metadata is stale; run scripts/export_agent_tool_reference.py"
            )
    else:
        MANUAL.write_text(text)
        MANIFEST.write_text(manifest)
    print(f"Agent manual: {len(text.splitlines())} lines, live tool routing verified")


if __name__ == "__main__":
    main()
