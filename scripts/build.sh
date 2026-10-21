#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
.venv/bin/python -c 'from lonora_agent.skills.registry import validate_resources; from lonora_tools.loader import load_tools; validate_resources({tool.name for tool in load_tools().definitions()})'
.venv/bin/python scripts/export_agent_tool_reference.py --check
pnpm lint
pnpm check
pnpm build
