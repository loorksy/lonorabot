#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m alembic -c packages/db/alembic.ini upgrade head
