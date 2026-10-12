#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ -z "$(git status --porcelain)" ]] || { echo 'Deployment checkout has local changes.' >&2; exit 1; }
git fetch origin main
git merge --ff-only origin/main
compose='infra/compose/docker-compose.prod.yml'
docker compose --env-file .env -f "$compose" pull
# Back up an existing installation before migrations change the schema.
if [[ -n "$(docker compose --env-file .env -f "$compose" ps -q db)" ]]; then LONORA_COMPOSE_FILE="$compose" bash scripts/backup.sh; fi
docker compose --env-file .env -f "$compose" up -d --wait
echo 'Main deployed. Check the authenticated workspace and /ready through your domain.'
