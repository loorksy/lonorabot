#!/usr/bin/env bash
# serve.sh <pkg> [--no-build]: build the package's web app, (re)start its API server on its port,
# refresh the signed-in seed ($FX_DIR/seed.json). Run again after every change you want to see live.
set -euo pipefail
PKG=$1; . /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/$PKG/env.sh; cd "$ROOT"
if [ "${2:-}" != "--no-build" ]; then
  /tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx/slot.sh pnpm --filter @lonora/web exec vite build --outDir ../../.runtime/ui-reference-web --emptyOutDir > "$FX_DIR/build.log" 2>&1 \
    || { echo "BUILD FAILED: see $FX_DIR/build.log"; tail -25 "$FX_DIR/build.log"; exit 1; }
fi
[ -f "$FX_DIR/server.pid" ] && kill "$(cat "$FX_DIR/server.pid")" 2>/dev/null || true
for i in $(seq 1 20); do curl -s --noproxy '*' -o /dev/null "http://127.0.0.1:$FX_PORT/health" || break; sleep 0.5; done
nohup .venv/bin/lonora-api --host 127.0.0.1 --port "$FX_PORT" > "$FX_DIR/server.log" 2>&1 &
echo $! > "$FX_DIR/server.pid"
for i in $(seq 1 120); do
  curl -s --noproxy '*' -o /dev/null -f "http://127.0.0.1:$FX_PORT/health" && break
  [ "$i" = 120 ] && { echo "SERVER DID NOT START: see $FX_DIR/server.log"; tail -25 "$FX_DIR/server.log"; exit 1; }
  sleep 0.5
done
echo '{"action":"init"}' | .venv/bin/python tests/ui-reference/seed_reference.py > "$FX_DIR/seed.json.new" 2> "$FX_DIR/seed.log" \
  && mv "$FX_DIR/seed.json.new" "$FX_DIR/seed.json" || { echo "SEED FAILED: see $FX_DIR/seed.log"; tail -15 "$FX_DIR/seed.log"; exit 1; }
.venv/bin/python tests/ui-reference/seed_domain.py < "$FX_DIR/seed.json" > "$FX_DIR/seed-domain.json" 2>> "$FX_DIR/seed.log" || echo "note: seed_domain failed (see $FX_DIR/seed.log); the base seed is in place"
echo "serving $PKG at http://localhost:$FX_PORT (seed: $FX_DIR/seed.json)"
