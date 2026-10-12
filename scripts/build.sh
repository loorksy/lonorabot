#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
pnpm lint
pnpm build
