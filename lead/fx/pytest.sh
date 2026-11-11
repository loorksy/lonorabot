#!/usr/bin/env bash
# pytest.sh <pkg> <pytest args...>: run pytest in the package worktree against its *_test database.
PKG=$1; shift; . /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/$PKG/env.sh; cd "$ROOT"
export LONORA_DATABASE_URL=$FX_TEST_DATABASE_URL LONORA_TASK_TEST_DATABASE_URL=$FX_TEST_DATABASE_URL
exec /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/slot.sh .venv/bin/python -m pytest -q -p no:cacheprovider "$@"
