#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --wait db
bash scripts/migrate.sh
mkdir -p .runtime
.venv/bin/lonora-api >.runtime/api.log 2>&1 & api_pid=$!
.venv/bin/lonora-gateway >.runtime/gateway.log 2>&1 & gateway_pid=$!
cleanup(){ kill "$api_pid" "$gateway_pid" 2>/dev/null || true; wait "$api_pid" "$gateway_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for attempt in {1..40}; do
    if curl -fsS http://localhost:8000/health >/dev/null; then break; fi
    kill -0 "$api_pid" 2>/dev/null || { tail -20 .runtime/api.log; exit 1; }
    sleep .5
done
curl -fsS http://localhost:8000/health >/dev/null
echo 'Lonora API and built Web: port 8000. Logs: .runtime/api.log and .runtime/gateway.log.'
wait -n "$api_pid" "$gateway_pid"
