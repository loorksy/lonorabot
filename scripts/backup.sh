#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
backup_root="${LONORA_BACKUP_ROOT:-backups}"
mkdir -p "$backup_root"
destination="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$destination"
if [[ -n "${LONORA_COMPOSE_FILE:-}" ]]; then
    docker compose --env-file .env -f "$LONORA_COMPOSE_FILE" exec -T db pg_dump -U lonora -d lonora -Fc >"$destination/database.dump"
else
    docker compose exec -T db pg_dump -U lonora -d lonora -Fc >"$destination/database.dump"
fi
tar -czf "$destination/files.tar.gz" --ignore-failed-read .env .runtime/artifacts
sha256sum "$destination/database.dump" "$destination/files.tar.gz" >"$destination/SHA256SUMS"
echo "Encrypted provider keys, database and artifacts saved to $destination. Protect this directory: it includes the encryption key."
