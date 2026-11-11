#!/usr/bin/env bash
# Local merge gate the lead ran on every PR head. Usage: gate.sh <worktree> <label> [check scripts...]
# Logs go to $GATE_OUT/gate-<label>/ (default /tmp). NOPW=1 skips Playwright.
# Needs: PostgreSQL 16 on 127.0.0.1:5432 with role lonora/ci-only-password, pnpm, a repo .venv, Chrome.
set -u
WT=$1; L=$2; shift 2
O=${GATE_OUT:-/tmp}/gate-$L; mkdir -p "$O"
cd "$WT"
export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=   # test-only
export LONORA_BOOTSTRAP_TOKEN=ci-only-bootstrap-token-32-characters          # test-only
export LONORA_COOKIE_SECURE=false
PP=""; for d in packages/*/src apps/*/src; do PP="$PP:$WT/$d"; done; export PYTHONPATH=${PP#:}
mkdb(){ sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $1 WITH (FORCE);" -c "CREATE DATABASE $1 OWNER lonora;" >/dev/null; }
step(){ local n=$1; shift; local t=$(date +%s); "$@" > "$O/$n.log" 2>&1; local rc=$?; echo "$n rc=$rc $(( $(date +%s)-t ))s" | tee -a "$O/summary.txt"; }
: > "$O/summary.txt"
step install pnpm install --frozen-lockfile --prefer-offline
step lint pnpm lint
step check pnpm check
step build pnpm build
step webunit pnpm exec tsx --test tests/web/*.test.ts
DB=gate_${L}_test; mkdb "$DB"
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/$DB
export LONORA_TASK_TEST_DATABASE_URL=$LONORA_DATABASE_URL
step migrate bash scripts/migrate.sh
step pytest timeout 3000 .venv/bin/python -m pytest -q --ignore=tests/test_web_browser.py -p no:cacheprovider
for c in "$@"; do mkdb "$DB"; step "migrate-$c" bash scripts/migrate.sh; step "$c" timeout 900 .venv/bin/python "tests/$c.py"; done
if [ "${NOPW:-0}" = 1 ]; then echo DONE-NOPW | tee -a "$O/summary.txt"; exit 0; fi
mkdb "gate_${L}_ci"
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/gate_${L}_ci
step migrate-pw bash scripts/migrate.sh
LONORA_UI_TEST_BROWSER_PATH=${LONORA_UI_TEST_BROWSER_PATH:-/usr/bin/google-chrome} step playwright timeout 3600 pnpm exec playwright test --trace off
sed 's/\x1b\[[0-9;]*m//g' "$O/playwright.log" | grep -E "^\s+[0-9]+\) |[0-9]+ (passed|failed|flaky|skipped)" > "$O/pw-summary.txt"
echo DONE | tee -a "$O/summary.txt"
