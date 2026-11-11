#!/usr/bin/env sh
set -eu
service="${1:-api}"
case "$service" in
  api)
    if [ "$#" -gt 0 ]; then shift; fi
    # The canonical production Compose runs migrations as their own step (`lonora update`).
    if [ "${LONORA_MIGRATE_ON_START:-true}" = true ]; then python -m alembic -c /app/packages/db/alembic.ini upgrade head; fi
    exec lonora-api "$@" ;;
  gateway) if [ "$#" -gt 0 ]; then shift; fi; exec lonora-gateway "$@" ;;
  migrate) if [ "$#" -gt 0 ]; then shift; fi; exec python -m alembic -c /app/packages/db/alembic.ini upgrade head "$@" ;;
  *) exec "$@" ;;
esac
