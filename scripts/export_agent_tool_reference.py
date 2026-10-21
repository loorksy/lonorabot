"""Export the exact registered Agent contracts into the operating manual.

Use --check in CI. This does not grant or load tools and requires no network/DB.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "packages/agent-runtime/resources/system/lonora.md"
MANIFEST = MANUAL.with_name("manifest.json")
MARKER = "<!-- tool-reference:generated -->"
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


def readable_json(value: Any, depth: int = 0) -> str:
    """Full JSON; scalar arrays and shared definitions stay compact, never omitted."""
    if isinstance(value, dict):
        entries: list[str] = []
        for key, item in cast(dict[str, Any], value).items():
            if key == "$defs":
                body = (
                    "{\n"
                    + ",\n".join(
                        "  " * (depth + 2)
                        + json.dumps(name)
                        + ": "
                        + json.dumps(definition, ensure_ascii=False, sort_keys=True)
                        for name, definition in cast(dict[str, Any], item).items()
                    )
                    + "\n"
                    + "  " * (depth + 1)
                    + "}"
                )
            else:
                body = readable_json(item, depth + 1)
            entries.append("  " * (depth + 1) + json.dumps(key) + ": " + body)
        return "{\n" + ",\n".join(entries) + "\n" + "  " * depth + "}" if entries else "{}"
    if isinstance(value, list) and any(
        isinstance(item, (dict, list)) for item in cast(list[Any], value)
    ):
        return (
            "[\n"
            + ",\n".join(
                "  " * (depth + 1) + readable_json(item, depth + 1)
                for item in cast(list[Any], value)
            )
            + "\n"
            + "  " * depth
            + "]"
        )
    return json.dumps(value, ensure_ascii=False)


def export() -> tuple[str, str]:
    registry = load_tools()
    text = MANUAL.read_text().split(MARKER)[0].rstrip() + "\n\n" + MARKER + "\n"
    text += "## Exact registered tool contracts\n\nThese contracts are generated from live registration. They document availability, not permission.\nDefinitions include all referenced input types. The actual supplied schema always wins.\n"
    mapping: dict[str, str] = {}
    for name, tool in registry.tools.items():
        module = tool.handler.__module__.rsplit(".", 1)[-1]
        mapping[name] = MODULE_POLICY[module]
        definition = tool.definition()
        text += f"\n### {name}\n{tool.description}\n"
        text += f"Effect metadata: read_only={str(tool.read_only).lower()}, financial={str(tool.financial).lower()}, replay_safe={str(tool.replay_safe).lower()}.\n"
        text += "```json\n" + readable_json(definition.parameters) + "\n```\n"
    text += "\n<!-- /tool-reference -->\n"
    manifest = (
        json.dumps(
            {
                "version": 1,
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
                "Agent manual tool contracts are stale; run scripts/export_agent_tool_reference.py"
            )
    else:
        MANUAL.write_text(text)
        MANIFEST.write_text(manifest)
    print(f"Agent manual: {len(text.splitlines())} lines, exact registered contracts verified")


if __name__ == "__main__":
    main()
