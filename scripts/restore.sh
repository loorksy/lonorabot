#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backup="${1:?Usage: restore.sh BACKUP_DIRECTORY --replace}"
[[ "${2:-}" == '--replace' ]] || { echo 'Stop API/Gateway first. --replace explicitly authorizes database replacement.' >&2; exit 1; }
[[ -f "$backup/database.dump" && -f "$backup/files.tar.gz" ]] || exit 1
(cd "$backup"; sha256sum -c SHA256SUMS)
# Validate archive paths before extraction, then restore the original encryption key.
.venv/bin/python - "$backup/files.tar.gz" <<'PY'
import sys,tarfile
with tarfile.open(sys.argv[1]) as archive:
    for item in archive.getmembers():
        if item.name!='.env' and not item.name.startswith('.runtime/artifacts'): raise SystemExit('Unexpected backup entry')
        if item.issym() or item.islnk() or '..' in item.name.split('/'): raise SystemExit('Unsafe backup entry')
    archive.extractall('.',filter='data')
PY
if [[ -n "${LONORA_COMPOSE_FILE:-}" ]]; then
    docker compose --env-file .env -f "$LONORA_COMPOSE_FILE" exec -T db pg_restore -U lonora -d lonora --clean --if-exists --exit-on-error <"$backup/database.dump"
else
    docker compose exec -T db pg_restore -U lonora -d lonora --clean --if-exists --exit-on-error <"$backup/database.dump"
fi
if [[ -f "$backup/artifacts.tar.gz" && -n "${LONORA_COMPOSE_FILE:-}" ]]; then
    docker compose --env-file .env -f "$LONORA_COMPOSE_FILE" run --rm --no-deps --entrypoint tar api -C /app -xzf - <"$backup/artifacts.tar.gz"
fi
echo 'Restore completed. Start API/Gateway and check /ready.'
