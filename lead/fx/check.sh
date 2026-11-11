#!/usr/bin/env bash
# check.sh <pkg> <name>: run tests/<name>.py (a check_*.py or *_browser.py script) on a fresh migrated database.
PKG=$1; NAME=$2; . /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/$PKG/env.sh; cd "$ROOT"
DB=lonora_fx_${PKG}_verify
sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $DB WITH (FORCE);" -c "CREATE DATABASE $DB OWNER lonora;" >/dev/null
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/$DB
export LONORA_TASK_TEST_DATABASE_URL=$LONORA_DATABASE_URL
bash scripts/migrate.sh >/dev/null 2>&1 && exec /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/slot.sh timeout 900 .venv/bin/python "tests/$NAME.py"
