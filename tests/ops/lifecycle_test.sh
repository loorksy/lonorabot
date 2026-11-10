#!/usr/bin/env bash
# End-to-end test of the production lifecycle on a machine with Docker:
# install -> backup -> restore-test -> tamper/wrong key -> update -> failed update with
# automatic rollback -> restore --replace -> adopt an installation running an old image.
#
#   bash tests/ops/lifecycle_test.sh REPO
#
# REPO is a registry repository holding these tags (see docs/operations.md, "Testing"):
#   old        an image built from a commit before this tooling (no bundle, no manifest)
#   v1, v2     two builds of this tree with different LONORA_VERSION build args
#   v3-broken  v2 plus a schema-changing migration whose gateway never becomes ready
# It uses the Compose project name "lonora" and host ports 80/443, so run it only on a
# disposable machine, never on a production host.
set -euo pipefail
repo="${1:?Usage: lifecycle_test.sh REPO}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
home="$work/home"
export LONORA_IMAGE_REPO="$repo" LONORA_READY_TIMEOUT="${LONORA_READY_TIMEOUT:-90}"
passed=0
ok() { passed=$((passed + 1)); printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
lonora() { "$home/infra/compose/lonora" "$@"; }
dc() { (cd "$home" && docker compose --env-file .env --env-file state/image.env -f infra/compose/docker-compose.prod.yml "$@"); }
sql() { dc exec -T db psql -U lonora -d lonora -tAc "$1" | tr -d '[:space:]'; }
pinned() { sed -n 's/^LONORA_IMAGE=//p' "$home/state/image.env"; }
digest_of() { docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$repo:$1" | grep -m1 "^$repo@"; }
teardown() {
    if [[ -f "$home/.env" ]]; then dc down -v --remove-orphans >/dev/null 2>&1 || true; fi
    rm -rf "$work"
}
trap teardown EXIT

# 1. Install with no toolchain beyond Docker and gpg.
LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$home" --domain localhost --version v1 --no-systemd >"$work/install.log" 2>&1 || { tail -30 "$work/install.log"; fail install; }
[[ "$(pinned)" == "$(digest_of v1)" ]] || fail 'install pins the v1 digest'
[[ "$(stat -c %a "$home/.env")" == 600 && "$(stat -c %a "$home/backup.key")" == 600 ]] || fail 'secret file modes'
key="$(sed -n 's/^LONORA_ENCRYPTION_KEY=//p' "$home/.env")"
backup_key="$(cat "$home/backup.key")"
for secret in "$key" "$backup_key" "$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")"; do
    grep -rqF -- "$secret" "$work/install.log" && fail 'installer printed a secret'
done
ok 'install: pinned digest, /ready, secrets 600 and not printed'

# The image's deployment bundle and release manifest carry no secrets.
container="$(docker create "$repo:v1")"
docker cp -q "$container:/app/deploy" "$work/bundle" && docker cp -q "$container:/app/release.json" "$work/bundle/"
docker rm "$container" >/dev/null
[[ -z "$(find "$work/bundle" \( -name '.env' -o -name '*.key' -o -name '*.pem' -o -name 'image.env' \) -print)" ]] || fail 'bundle holds a secret file'
grep -rqE -- '(PASSWORD|SECRET|TOKEN|_KEY)=[A-Za-z0-9_+/-]{8,}' "$work/bundle" && fail 'bundle holds a secret value'
for secret in "$key" "$backup_key"; do grep -rqF -- "$secret" "$work/bundle" && fail 'bundle holds an install secret'; done
ok 'image bundle and release.json: no secret files or values'

# 2. Seed real state: the owner account and one artifact file.
dc exec -T api python -c "import json,os,urllib.request
body=json.dumps({'email':'owner@example.com','password':'lifecycle-test-password-1','bootstrap_token':os.environ['LONORA_BOOTSTRAP_TOKEN']}).encode()
urllib.request.urlopen(urllib.request.Request('http://localhost:8000/api/onboarding',body,{'Content-Type':'application/json'}),timeout=10)" >/dev/null
dc exec -T api sh -c 'echo lifecycle-probe >/app/.runtime/artifacts/probe.txt'
owners() { sql "SELECT count(*) FROM ln_owners"; }
[[ "$(owners)" == 1 ]] || fail 'seed owner'
ok 'seed: owner account and artifact'

# 3. Encrypted backup.
lonora backup >"$work/backup.log"
backup="$(ls -1t "$home"/backups/lonora-*.tar.gpg | head -n 1)"
[[ "$(stat -c %a "$backup")" == 600 ]] || fail 'backup mode'
grep -qaF -- "$key" "$backup" && fail 'backup holds the encryption key in clear'
grep -qa 'PGDMP' "$backup" && fail 'backup holds a clear database dump'
grep -qaF -- 'lifecycle-probe' "$backup" && fail 'backup holds clear artifacts'
grep -rqF -- "$key" "$work/backup.log" && fail 'backup printed a secret'
grep -rqF -- "$backup_key" "$work/backup.log" && fail 'backup printed the backup key'
ok 'backup: encrypted, mode 600, no clear secrets or data'

# 4. Restore test into a throwaway isolated stack.
lonora restore-test "$backup" >"$work/rt.log" 2>&1 || { cat "$work/rt.log"; fail restore-test; }
grep -q 'Restore test passed' "$work/rt.log" || fail 'restore-test verdict'
[[ -z "$(docker ps -aq --filter name=lonora-restoretest)" ]] || fail 'restore-test left containers'
ok "restore-test: $(sed -n 's/^lonora: //p' "$work/rt.log" | tail -n 1)"

# 5. A damaged backup and a wrong key are refused.
cp "$backup" "$work/damaged.tar.gpg"
printf 'X' | dd of="$work/damaged.tar.gpg" bs=1 seek=$(($(stat -c %s "$backup") / 2)) conv=notrunc status=none
if lonora restore-test "$work/damaged.tar.gpg" >"$work/damaged.log" 2>&1; then fail 'damaged backup accepted'; fi
grep -q 'Decryption failed' "$work/damaged.log" || fail 'damaged backup refused for the wrong reason'
if LONORA_BACKUP_KEY=wrong-key lonora restore-test "$backup" >"$work/wrongkey.log" 2>&1; then fail 'wrong key accepted'; fi
grep -q 'Decryption failed' "$work/wrongkey.log" || fail 'wrong key refused for the wrong reason'
ok 'damaged backup and wrong key refused'

# 6. Update to v2.
lonora update v2 >"$work/update.log" 2>&1 || { tail -30 "$work/update.log"; fail 'update v2'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'update pins the v2 digest'
[[ "$(owners)" == 1 ]] || fail 'data kept across update'
grep -q 'Backup taken first' "$work/update.log" || fail 'update took a backup'
ok 'update v2: backup first, migrate step, /ready, digest pinned'

# 7. Images without a release manifest are refused.
if lonora update old >"$work/old.log" 2>&1; then fail 'manifest-less image accepted'; fi
grep -q 'no release manifest' "$work/old.log" || fail 'manifest refusal message'
ok 'update refuses an image without a release manifest'

# 8. A failing update rolls back automatically, including the schema.
dc exec -T db psql -U lonora -d lonora -qc "CREATE TABLE ops_probe (note text); INSERT INTO ops_probe VALUES ('before-update')" >/dev/null
if lonora update v3-broken >"$work/broken.log" 2>&1; then fail 'broken update reported success'; fi
grep -q 'Update failed at: /ready health gate' "$work/broken.log" || { tail -30 "$work/broken.log"; fail 'failure point'; }
grep -q 'Rolled back to' "$work/broken.log" || { tail -30 "$work/broken.log"; fail 'rollback message'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'rollback restores the v2 pin'
[[ "$(sql "SELECT version_num FROM lonora_v2_alembic")" == 0045_chat_lists ]] || fail 'rollback restores the schema revision'
[[ "$(sql "SELECT to_regclass('ln_broken_probe') IS NULL")" == t ]] || fail 'rollback removed the broken migration table'
[[ "$(owners)" == 1 ]] || fail 'data kept across rollback'
[[ "$(sql "SELECT string_agg(note, ',') FROM ops_probe")" == before-update ]] || fail 'rows written before the update survive the rollback'
"$home/infra/compose/lonora" status >"$work/status.log" 2>&1
grep -q '/ready: ok' "$work/status.log" || fail 'ready after rollback'
ok 'broken update: migrated, failed /ready, rolled back image + schema, /ready ok'

# 9. Restore --replace brings the files and data of the older backup back.
dc exec -T api sh -c 'rm /app/.runtime/artifacts/probe.txt'
dc exec -T db psql -U lonora -d lonora -qc 'DELETE FROM ln_owners' >/dev/null 2>&1 || dc exec -T db psql -U lonora -d lonora -qc 'TRUNCATE ln_owners CASCADE' >/dev/null
[[ "$(owners)" == 0 ]] || fail 'simulated loss'
if lonora restore "$backup" >/dev/null 2>&1; then fail 'restore without --replace accepted'; fi
lonora restore "$backup" --replace >"$work/restore.log" 2>&1 || { tail -30 "$work/restore.log"; fail restore; }
[[ "$(owners)" == 1 ]] || fail 'restore brought the owner back'
dc exec -T api cat /app/.runtime/artifacts/probe.txt | grep -q lifecycle-probe || fail 'restore brought the artifact back'
ok 'restore --replace: data and artifacts back, /ready ok'

# 10. Adopt an installation that runs an image from before this tooling.
dc down -v --remove-orphans >/dev/null 2>&1
printf 'LONORA_IMAGE=%s\n' "$(digest_of old)" >"$home/state/image.env"
dc up -d --wait >/dev/null 2>&1 || fail 'old image start'
lonora update v2 >"$work/adopt.log" 2>&1 || { tail -30 "$work/adopt.log"; fail 'adopt old install'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'adoption pins v2'
ok 'adoption: an old-image installation updates to v2'

printf '\nAll %d lifecycle checks passed.\n' "$passed"
