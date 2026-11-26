#!/usr/bin/env bash
# The one gate (VISION 14.1.2): run it in full before every merge to main.
# .github/workflows/ci.yml runs this same script.
#
# Needs a PostgreSQL server (never a production one) whose role may create databases, named by
# LONORA_DATABASE_URL. Only its server and role are used: each step gets a fresh database, dropped
# when the gate ends.
# One-time setup: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`,
# `.venv/bin/python scripts/cache_model_tokenizers.py`, `pnpm install --frozen-lockfile` and
# `pnpm exec playwright install chromium`. Steps run cheapest first and stop at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVER=${LONORA_DATABASE_URL:?set LONORA_DATABASE_URL to a PostgreSQL server where the gate may create databases}
# CI-only dummy values, never a production key or token.
export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=
export LONORA_BOOTSTRAP_TOKEN=ci-only-bootstrap-token-32-characters
export LONORA_COOKIE_SECURE=false
export LONORA_AUTH_RATE_LIMIT_PER_MINUTE=10000
# The code of this checkout, whatever the virtualenv's editable install points at.
PYTHONPATH=$(printf '%s:' "$PWD"/packages/*/src "$PWD"/apps/*/src)
export PYTHONPATH=${PYTHONPATH%:}
PY=.venv/bin/python
RUN=$$_$(date +%s)
CREATED=()

step() { printf '\n== %s\n' "$*"; }

# database create|drop NAME, on SERVER; create prints the new database's URL. SERVER goes in the
# environment: any user of the machine can read a command line, password included.
database() {
  GATE_SERVER=$SERVER "$PY" - "$1" "$2" <<'PY'
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

server, action, name = make_url(os.environ["GATE_SERVER"]), sys.argv[1], sys.argv[2]
statement = (
    f"CREATE DATABASE {name}" if action == "create" else f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"
)


async def run() -> None:
    engine = create_async_engine(server.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


asyncio.run(run())
if action == "create":
    print(server.set(database=name).render_as_string(hide_password=False))
PY
}

cleanup() {
  for name in "${CREATED[@]}"; do database drop "$name" || true; done
}
trap cleanup EXIT

# fresh NAME: a new migrated database, exported as the one every later command uses.
fresh() {
  local name=lonora_gate_${RUN}_$1_test
  CREATED+=("$name")
  LONORA_DATABASE_URL=$(database create "$name")
  export LONORA_DATABASE_URL LONORA_TASK_TEST_DATABASE_URL=$LONORA_DATABASE_URL
  bash scripts/migrate.sh
}

step "build: ruff, pyright, the policy, tool-reference and manifest checks, pnpm lint, check and build"
bash scripts/build.sh

step "web catalogs: extracted, and no Arabic translation missing"
# The extraction rewrites the tracked catalogs (their source line references). Catalogs without
# local edits are restored afterwards, so the gate leaves the checkout as it found it.
catalogs=apps/web/src/i18n/locales
git diff --quiet -- "$catalogs" && restore=1 || restore=0
pnpm --filter @lonora/web i18n
missing=$(awk '$0 == "msgstr \"\"" && previous ~ /^msgid ".+"$/ { missing++ } { previous = $0 } END { print missing + 0 }' "$catalogs"/ar/messages.po)
[ "$restore" -eq 0 ] || git checkout -q -- "$catalogs"
[ "$missing" -eq 0 ] || { echo "Arabic catalog: $missing messages have no translation (pnpm --filter @lonora/web i18n adds them)"; exit 1; }

step "migrate a fresh database: exactly one alembic head"
fresh tests
heads=$("$PY" -m alembic -c packages/db/alembic.ini heads | grep -c '(head)' || true)
[ "$heads" -eq 1 ] || { echo "expected one alembic head, found $heads"; exit 1; }

# The full run includes tests/test_acceptance_scenario.py, which runs
# scripts/agent_eval/acceptance.py --offline and holds its known defects strictly.
step "full pytest"
"$PY" -m pytest -q tests

step "foundation checks, each on its own fresh database"
"$PY" tests/run_foundation_checks.py --isolated-databases

step "TypeScript unit tests"
pnpm exec tsx --test tests/web/*.test.ts tests/mobile/*.test.ts

# Ports 8830 and 8831 are fixed: the suites run one at a time.
step "web Playwright suite"
fresh web
pnpm test:web --trace off

step "mobile Playwright suite"
fresh mobile
pnpm test:mobile --trace off

step "gate passed"
