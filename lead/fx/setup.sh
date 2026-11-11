#!/usr/bin/env bash
# setup.sh <pkg> <port>: worktree /home/user/wt/<pkg> on branch fx/<pkg>, deps, databases, env file.
set -euo pipefail
PKG=$1; PORT=$2
MAIN=/home/user/lonorabot; WT=/home/user/wt/$PKG; D=/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/$PKG
mkdir -p /home/user/wt "$D/shots"
cd $MAIN
[ -d "$WT" ] || git worktree add -q -b "fx/$PKG" "$WT" ccr-9c66a289-3283wb
ln -sfn $MAIN/.venv "$WT/.venv"
cat > "$D/env.sh" <<ENV
# Test-only values for package $PKG. Source it: . $D/env.sh
export ROOT=$WT
export FX_PKG=$PKG FX_PORT=$PORT FX_DIR=$D
export LONORA_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=
export LONORA_BOOTSTRAP_TOKEN=lonora-ui-reference-ci-only-2026
export LONORA_COOKIE_SECURE=false
export LONORA_AUTH_RATE_LIMIT_PER_MINUTE=10000
export LONORA_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/lonora_fx_${PKG}_ci
export FX_TEST_DATABASE_URL=postgresql+asyncpg://lonora:ci-only-password@127.0.0.1:5432/lonora_fx_${PKG}_test
export LONORA_ALLOWED_ORIGIN=http://localhost:$PORT
export LONORA_WEB_ROOT=$WT/.runtime/ui-reference-web
export LONORA_CHART_RENDERER_ROOT=$WT/.runtime/ui-reference-web
export LONORA_ARTIFACT_ROOT=$WT/.runtime/ui-reference-artifacts
export LONORA_UI_TEST_EMAIL=ahmed@example.com
export LONORA_UI_TEST_PASSWORD=ci-only-owner-password
export LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome
export NODE_ENV=production
PP=""; for d in $WT/packages/*/src $WT/apps/*/src; do PP="\$PP:\$d"; done; export PYTHONPATH=\${PP#:}
unset AI_AGENT CLAUDECODE
ENV
. "$D/env.sh"
cd "$WT"
/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/slot.sh pnpm install --frozen-lockfile --prefer-offline > "$D/install.log" 2>&1
for db in lonora_fx_${PKG}_ci lonora_fx_${PKG}_test; do
  sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $db WITH (FORCE);" -c "CREATE DATABASE $db OWNER lonora;" >/dev/null
done
bash scripts/migrate.sh > "$D/migrate.log" 2>&1
LONORA_DATABASE_URL=$FX_TEST_DATABASE_URL bash scripts/migrate.sh >> "$D/migrate.log" 2>&1
echo "setup $PKG ok"
