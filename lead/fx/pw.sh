#!/usr/bin/env bash
# pw.sh <pkg> <spec files or -g pattern...>: run repo Playwright specs (tests/web/*.spec.mjs) from the package
# worktree. The suite's port (8830) is shared by the whole machine, so runs are serialised: this may wait.
PKG=$1; shift; . /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/$PKG/env.sh; cd "$ROOT"
DB=lonora_fx_${PKG}_pw_ci
exec 9>/tmp/fx-playwright.lock; flock 9
sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $DB WITH (FORCE);" -c "CREATE DATABASE $DB OWNER lonora;" >/dev/null
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/$DB
export LONORA_BOOTSTRAP_TOKEN=ci-only-bootstrap-token-32-characters
unset LONORA_ALLOWED_ORIGIN LONORA_WEB_ROOT LONORA_CHART_RENDERER_ROOT LONORA_ARTIFACT_ROOT NODE_ENV
bash scripts/migrate.sh >/dev/null 2>&1 || { echo "migrate failed"; exit 1; }
timeout 2400 pnpm exec playwright test --trace off "$@"
