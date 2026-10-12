#!/usr/bin/env sh
set -eu
case "${1:-api}" in
  api) python -m alembic -c /app/packages/db/alembic.ini upgrade head; exec lonora-api ;;
  gateway) exec lonora-gateway ;;
  migrate) exec python -m alembic -c /app/packages/db/alembic.ini upgrade head ;;
  *) exec "$@" ;;
esac
