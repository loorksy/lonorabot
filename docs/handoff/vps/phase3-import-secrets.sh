#!/usr/bin/env bash
# Phase 3: after the owner has created the owner account on the NEW install, carry the 3 DB secrets
# (provider/openai, provider/zai, broker/<MetaApi account>) from the OLD lonora-db into the new install.
# Ciphertext stays encrypted in transit (both installs share LONORA_ENCRYPTION_KEY via --env-from);
# values are decrypted only inside the new api container and never printed.
# Usage (from this directory on the VPS): bash phase3-import-secrets.sh
set -euo pipefail
umask 077
here="$(cd "$(dirname "$0")" && pwd)"
OUT="$(mktemp /root/lonora-secret-export.XXXXXX.json)"
trap 'shred -u "$OUT" 2>/dev/null || rm -f "$OUT"' EXIT
docker exec -i lonora-db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1' < "$here/export-secrets.sql" > "$OUT"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("export:", len(d["secrets"]), "secrets,", len(d["brokers"]), "broker rows")' "$OUT"
API=$(docker ps --filter label=com.docker.compose.project=lonora2 --filter label=com.docker.compose.service=api --format '{{.Names}}' | head -1)
[ -n "$API" ] || { echo "STOP: the new api container (project lonora2) is not running"; exit 1; }
install -m 644 "$here/import_secrets.py" /tmp/lonora-import_secrets.py
docker cp /tmp/lonora-import_secrets.py "$API:/tmp/import_secrets.py"; rm -f /tmp/lonora-import_secrets.py
set +e
docker exec -i -w /app "$API" sh -c 'umask 077; cat > /tmp/export.json && python /tmp/import_secrets.py /tmp/export.json; rc=$?; rm -f /tmp/export.json /tmp/import_secrets.py; exit $rc' < "$OUT"
rc=$?
set -e
echo "import rc=$rc (0 = all imported or already present)"
exit $rc
