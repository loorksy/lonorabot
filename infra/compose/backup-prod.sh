#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export LONORA_COMPOSE_FILE=infra/compose/docker-compose.prod.yml
exec bash scripts/backup.sh
