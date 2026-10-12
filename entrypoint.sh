#!/usr/bin/env sh
set -eu
service="${1:-api}"
case "$service" in
  api) if [ "$#" -gt 0 ]; then shift; fi; python -m alembic -c /app/packages/db/alembic.ini upgrade head; exec lonora-api "$@" ;;
  gateway) if [ "$#" -gt 0 ]; then shift; fi; exec lonora-gateway "$@" ;;
  migrate) if [ "$#" -gt 0 ]; then shift; fi; exec python -m alembic -c /app/packages/db/alembic.ini upgrade head "$@" ;;
  *) exec "$@" ;;
esac
