#!/usr/bin/env bash
# End-to-end test of the production lifecycle against real Docker (docs/operations.md,
# "Testing"). Each review finding of PR #43 has a check here.
#
#   bash tests/ops/lifecycle_test.sh REPO
#
# REPO is a registry repository holding these tags; tests/ops/build_test_images.sh REPO
# builds and pushes all five:
#   old        an image built from a commit before this tooling (no bundle, no manifest)
#   v1, v2     two builds of this tree with different LONORA_VERSION build args
#   v3-broken  v2 plus a schema-changing migration whose gateway never becomes ready
#   v4-good    v2 plus a working migration (9998_good_probe)
# It uses the Compose project name "lonora", its volume names and ports 80/443, so it
# refuses to run where a Lonora installation exists. Use a disposable machine.
set -euo pipefail
repo="${1:?Usage: lifecycle_test.sh REPO}"
root="$(cd "$(dirname "$0")/../.." && pwd)"

# Never run next to a real installation: it would share its project and volumes.
if docker volume inspect lonora_database >/dev/null 2>&1 || [[ -e /opt/lonora/state ]] ||
    [[ -n "$(docker ps -aq --filter label=com.docker.compose.project=lonora)" ]]; then
    echo 'Refusing to run: this host has a Lonora installation (volume lonora_database, /opt/lonora/state or project containers).' >&2
    exit 1
fi

work="$(mktemp -d)"
home="$work/home"
# The migration head of v1/v2 (main's head when the images were built).
base_head="$(docker run --rm --network none --entrypoint cat "$repo:v2" /app/release.json | sed -n 's/.*"migration_head": "\([^"]*\)".*/\1/p')"
[[ -n "$base_head" ]] || { echo "No migration head in $repo:v2" >&2; exit 1; }
export LONORA_IMAGE_REPO="$repo" LONORA_READY_TIMEOUT="${LONORA_READY_TIMEOUT:-90}"
passed=0
ok() { passed=$((passed + 1)); printf 'PASS %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*" >&2; exit 1; }
show() { tail -30 "$1" >&2; }
lonora() { "$home/infra/compose/lonora" "$@"; }
dc() { (cd "$home" && docker compose --env-file .env --env-file state/image.env -f infra/compose/docker-compose.prod.yml "$@"); }
sql() { dc exec -T db psql -U lonora -d lonora -tAc "$1" | tr -d '[:space:]'; }
pinned() { sed -n 's/^LONORA_IMAGE=//p' "$home/state/image.env"; }
digest_of() { docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$repo:$1" | grep -m1 "^$repo@"; }
owners() { sql "SELECT count(*) FROM ln_owners"; }
ready() { # /ready can miss a beat (gateway heartbeat) on a loaded machine: poll up to 60 s
    local deadline=$((SECONDS + 60))
    while ((SECONDS < deadline)); do
        lonora status >"$work/status.log" 2>&1 || true
        if grep -q '/ready: ok' "$work/status.log"; then return 0; fi
        sleep 3
    done
    show "$work/status.log"
    return 1
}
backups() { find "$home/backups" -maxdepth 1 -name 'lonora-*.tar.gpg' | wc -l; }
no_leftovers() {
    [[ -z "$(find "$home/backups" -mindepth 1 -maxdepth 1 \( -name '.work.*' -o -name '*.part' \))" ]] || fail "$1: plaintext work files left in backups/"
    [[ -z "$(find "$home" -maxdepth 1 -name '.env.merge.*')" ]] || fail "$1: merge files left"
}
install_fresh() { # $1 version
    LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$home" --domain localhost --version "$1" --no-systemd >"$work/install.log" 2>&1 || { show "$work/install.log"; fail "install $1"; }
}
wipe() { dc down -v --remove-orphans >/dev/null 2>&1 || true; rm -rf "$home"; }
teardown() {
    if [[ -f "$home/.env" ]]; then dc down -v --remove-orphans >/dev/null 2>&1 || true; fi
    rm -f /usr/local/bin/lonora
    rm -rf "$work"
}
trap teardown EXIT
gpg_key() { gpg --homedir "$work/gnupg" --batch --quiet --pinentry-mode loopback --passphrase-file "$home/backup.key" "$@"; }
mkdir -m 700 "$work/gnupg"

# 1. Install with no toolchain beyond Docker and gpg.
install_fresh v1
[[ "$(pinned)" == "$(digest_of v1)" ]] || fail 'install pins the v1 digest'
[[ "$(stat -c %a "$home/.env")" == 600 && "$(stat -c %a "$home/backup.key")" == 600 ]] || fail 'secret file modes'
[[ "$(stat -c %a "$home/infra/compose/Caddyfile.prod")" == 644 && "$(stat -c %a "$home/infra/compose/lonora")" == 755 ]] || fail 'bundle file modes'
key="$(sed -n 's/^LONORA_ENCRYPTION_KEY=//p' "$home/.env")"
backup_key="$(cat "$home/backup.key")"
first_password="$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")"
for secret in "$key" "$backup_key" "$first_password"; do
    if grep -qF -- "$secret" "$work/install.log"; then fail 'installer printed a secret'; fi
done
if LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$home" --domain localhost --version v1 --no-systemd >"$work/reinstall.log" 2>&1; then fail 'installer ran over an installation'; fi
grep -q 'already has an installation' "$work/reinstall.log" || fail 'reinstall refusal message'
ok 'install: digest pinned, /ready, secrets 600 and not printed, bundle modes 644/755, no second install over it'

# 2. The image's deployment bundle and release manifest carry no secrets.
container="$(docker create "$repo:v1")"
docker cp -q "$container:/app/deploy" "$work/bundle"
docker cp -q "$container:/app/release.json" "$work/bundle/"
docker rm "$container" >/dev/null
[[ -z "$(find "$work/bundle" \( -name '.env' -o -name '*.key' -o -name '*.pem' -o -name 'image.env' \) -print)" ]] || fail 'bundle holds a secret file'
if grep -rqE -- '(PASSWORD|SECRET|TOKEN|_KEY)=[A-Za-z0-9_+/-]{8,}' "$work/bundle"; then fail 'bundle holds a secret value'; fi
for secret in "$key" "$backup_key"; do
    if grep -rqF -- "$secret" "$work/bundle"; then fail 'bundle holds an install secret'; fi
done
ok 'image bundle and release.json: no secret files or values'

# 3. Seed real state: the owner account and one artifact file.
dc exec -T api python -c "import json,os,urllib.request
body=json.dumps({'email':'owner@example.com','password':'lifecycle-test-password-1','bootstrap_token':os.environ['LONORA_BOOTSTRAP_TOKEN']}).encode()
urllib.request.urlopen(urllib.request.Request('http://localhost:8000/api/onboarding',body,{'Content-Type':'application/json'}),timeout=10)" >/dev/null
dc exec -T api sh -c 'echo lifecycle-probe >/app/.runtime/artifacts/probe.txt'
[[ "$(owners)" == 1 ]] || fail 'seed owner'
ok 'seed: owner account and artifact'

# 4. Encrypted, verified backup; the plaintext markers exist only after decryption.
lonora backup >"$work/backup.log" 2>&1 || { show "$work/backup.log"; fail backup; }
b1="$(ls -1t "$home"/backups/lonora-*.tar.gpg | head -n 1)"
[[ "$(stat -c %a "$b1")" == 600 ]] || fail 'backup mode'
gpg_key --decrypt --output "$work/b1.tar" "$b1"
mkdir "$work/b1" && tar -C "$work/b1" -xf "$work/b1.tar"
grep -qa PGDMP "$work/b1/database.dump" || fail 'positive control: the decrypted dump is a pg_dump'
grep -qaF -- "$key" <(tar -xzOf "$work/b1/config.tar.gz" .env) || fail 'positive control: the decrypted config holds .env'
if grep -qa PGDMP "$b1"; then fail 'backup holds a clear database dump'; fi
if grep -qaF -- "$key" "$b1"; then fail 'backup holds the encryption key in clear'; fi
if grep -qaF -- lifecycle-probe "$b1"; then fail 'backup holds clear artifacts'; fi
for secret in "$key" "$backup_key"; do
    if grep -qF -- "$secret" "$work/backup.log"; then fail 'backup printed a secret (stdout or stderr)'; fi
done
if tar -tzf "$work/b1/config.tar.gz" | grep -q '^infra'; then fail 'backup carries deployment files'; fi
no_leftovers backup
ok 'backup: verified, encrypted (decrypted copy has the dump and .env, the file has neither), no deployment files, nothing printed'

# 5. Restore test into a throwaway isolated stack; no container or volume left behind.
volumes_before="$(docker volume ls -q | wc -l)"
lonora restore-test "$b1" >"$work/rt.log" 2>&1 || { show "$work/rt.log"; fail restore-test; }
grep -q 'Restore test passed' "$work/rt.log" || fail 'restore-test verdict'
[[ -z "$(docker ps -aq --filter name=lonora-restoretest)" ]] || fail 'restore-test left containers'
[[ "$(docker volume ls -q | wc -l)" == "$volumes_before" ]] || fail 'restore-test left a volume with the restored data'
no_leftovers restore-test
ok "restore-test: $(sed -n 's/^lonora: //p' "$work/rt.log" | tail -n 1)"

# 6. Damaged, wrong-key and forged (unencrypted) backups are refused.
cp "$b1" "$work/damaged.tar.gpg"
printf 'X' | dd of="$work/damaged.tar.gpg" bs=1 seek=$(($(stat -c %s "$b1") / 2)) conv=notrunc status=none
if lonora restore-test "$work/damaged.tar.gpg" >"$work/damaged.log" 2>&1; then fail 'damaged backup accepted'; fi
grep -q 'Decryption failed' "$work/damaged.log" || fail 'damaged backup refused for the wrong reason'
if LONORA_BACKUP_KEY=wrong-key lonora restore-test "$b1" >"$work/wrongkey.log" 2>&1; then fail 'wrong key accepted'; fi
grep -q 'Decryption failed' "$work/wrongkey.log" || fail 'wrong key refused for the wrong reason'
# A forged file: the genuine members, re-packed as a plaintext OpenPGP literal packet with
# an .env that points Compose at an attacker's overlay.
mkdir "$work/forged" && cp "$work/b1"/* "$work/forged/"
printf 'LONORA_COMPOSE_OVERLAYS=evil.yml\nLONORA_ENCRYPTION_KEY=forged\n' >"$work/forged/.env"
tar -C "$work/forged" -czf "$work/forged/config.tar.gz" .env && rm "$work/forged/.env"
(cd "$work/forged" && sha256sum database.dump artifacts.tar.gz config.tar.gz manifest.json >SHA256SUMS)
tar -C "$work/forged" -cf "$work/forged.tar" SHA256SUMS manifest.json database.dump artifacts.tar.gz config.tar.gz
gpg --homedir "$work/gnupg" --batch --quiet --store --output "$work/forged.tar.gpg" "$work/forged.tar"
env_before="$(sha256sum <"$home/.env")"
if lonora restore "$work/forged.tar.gpg" --replace --with-config >"$work/forged.log" 2>&1; then fail 'forged backup restored'; fi
grep -q 'not an authentic backup' "$work/forged.log" || { show "$work/forged.log"; fail 'forged backup refused for the wrong reason'; }
[[ "$(sha256sum <"$home/.env")" == "$env_before" ]] || fail 'forged backup changed .env'
ready || fail 'services after the forged restore attempt'
no_leftovers refusals
ok 'damaged file, wrong key and forged plaintext backup refused; nothing changed'

# 7. A failing or truncating pg_dump aborts the update before anything is changed.
pg_dump_breaks() { # $1: exit status of the broken pg_dump
    dc exec -T db sh -c "mv /usr/local/bin/pg_dump /usr/local/bin/pg_dump.real && printf '#!/bin/sh\n/usr/local/bin/pg_dump.real \"\$@\" | head -c 4000\nexit $1\n' >/usr/local/bin/pg_dump && chmod 755 /usr/local/bin/pg_dump"
}
pg_dump_heals() { dc exec -T db sh -c 'mv -f /usr/local/bin/pg_dump.real /usr/local/bin/pg_dump'; }
for mode in 1 0; do
    count="$(backups)"
    pg_dump_breaks "$mode"
    if lonora update v2 >"$work/dumpfail.log" 2>&1; then fail "update succeeded with a broken pg_dump (exit $mode)"; fi
    pg_dump_heals
    grep -q 'Backup failed; nothing was changed' "$work/dumpfail.log" || { show "$work/dumpfail.log"; fail "pg_dump exit $mode: abort message"; }
    [[ "$(pinned)" == "$(digest_of v1)" ]] || fail "pg_dump exit $mode: pin changed"
    [[ ! -e "$home/state/update-in-progress" ]] || fail "pg_dump exit $mode: marker left"
    [[ "$(backups)" == "$count" ]] || fail "pg_dump exit $mode: a bad backup was kept"
    [[ "$(owners)" == 1 ]] || fail "pg_dump exit $mode: live data changed"
    ready || fail "pg_dump exit $mode: services not back"
    no_leftovers "pg_dump exit $mode"
done
ok 'failed pg_dump (exit 1) and truncated pg_dump (exit 0): update aborted before pinning, live DB untouched, no bad backup kept'

# 8. Refusals that change nothing: concurrent operation, no pin, no release manifest.
exec 8>"$home/state/lock"
flock 8
if lonora update v2 >"$work/locked.log" 2>&1; then fail 'update ran while locked'; fi
grep -q 'Another lonora operation' "$work/locked.log" || fail 'lock message'
exec 8>&-
mv "$home/state/image.env" "$work/image.env.saved"
if (cd "$home" && LONORA_IMAGE_REPO="$repo" infra/compose/lonora update v2) >"$work/nopin.log" 2>&1; then fail 'update ran without a pin'; fi
mv "$work/image.env.saved" "$home/state/image.env"
grep -q 'No pinned image' "$work/nopin.log" || fail 'no-pin message'
if lonora update old >"$work/old.log" 2>&1; then fail 'manifest-less image accepted'; fi
grep -q 'no release manifest' "$work/old.log" || fail 'manifest refusal message'
ready || fail 'services after refusals'
ok 'refused without change: a second concurrent operation, no pinned image, an image without a release manifest'

# 9. Update to v2; the running script is replaced by rename, never rewritten in place.
inode_before="$(stat -c %i "$home/infra/compose/lonora")"
lonora update v2 >"$work/update.log" 2>&1 || { show "$work/update.log"; fail 'update v2'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'update pins the v2 digest'
[[ "$(owners)" == 1 ]] || fail 'data kept across update'
grep -q 'Backup taken first' "$work/update.log" || fail 'update took a backup'
grep -q 'Starting the API; the Gateway stays stopped' "$work/update.log" || fail 'API gated before the Gateway'
[[ "$(stat -c %i "$home/infra/compose/lonora")" != "$inode_before" ]] || fail 'script rewritten in place'
[[ "$(stat -c %a "$home/infra/compose/Caddyfile.prod")" == 644 ]] || fail 'bundle mode after update'
ok 'update v2: backup first, migrate step, API then Gateway, /ready, digest pinned, script replaced atomically'

# 10. A failing update with no financial writes rolls back image and schema.
dc exec -T db psql -U lonora -d lonora -qc "CREATE TABLE ops_probe (note text); INSERT INTO ops_probe VALUES ('before-update')" >/dev/null
if lonora update v3-broken >"$work/broken.log" 2>&1; then fail 'broken update reported success'; fi
grep -q 'Update failed at: /ready health gate' "$work/broken.log" || { show "$work/broken.log"; fail 'failure point'; }
grep -q 'Rolled back to' "$work/broken.log" || { show "$work/broken.log"; fail 'rollback message'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'rollback restores the v2 pin'
[[ "$(sql 'SELECT version_num FROM lonora_v2_alembic')" == "$base_head" ]] || fail 'rollback restores the schema revision'
[[ "$(sql "SELECT to_regclass('ln_broken_probe') IS NULL")" == t ]] || fail 'rollback removed the broken migration table'
[[ "$(sql "SELECT string_agg(note, ',') FROM ops_probe")" == before-update ]] || fail 'rows written before the update survive'
[[ "$(owners)" == 1 ]] || fail 'data kept across rollback'
ready || fail 'ready after rollback'
no_leftovers rollback
ok 'broken update: migrated, failed /ready, restored from the pre-update backup (no downgrade), earlier rows kept, /ready ok'

# 11. If the failed version wrote to the trading journal, the rollback holds instead of
# dropping the database; --force restores only when the owner chooses it.
lonora update v3-broken >"$work/money.log" 2>&1 &
updater=$!
until grep -q '^phase=gateway' "$home/state/update-in-progress" 2>/dev/null; do
    kill -0 "$updater" 2>/dev/null || fail 'update ended before the gateway phase'
    sleep 1
done
dc exec -T db psql -U lonora -d lonora -qc "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id, request_hash, request, status, result, submitted_at, updated_at) SELECT 'op-during-gate', id, 'acct', 'h', '{}', 'submitted', '{}', now(), now() FROM ln_owners LIMIT 1" >/dev/null
status=0; wait "$updater" || status=$?
[[ "$status" == 2 ]] || { show "$work/money.log"; fail "held rollback exit status ($status)"; }
grep -q 'ROLLBACK HELD' "$work/money.log" || fail 'hold message'
grep -q 'lonora rollback --force' "$work/money.log" || fail 'hold names the commands'
[[ "$(sql "SELECT count(*) FROM ln_trading_journal WHERE operation_id='op-during-gate'")" == 1 ]] || fail 'journal row kept while held'
[[ "$(pinned)" == "$(digest_of v3-broken)" ]] || fail 'held: the failed version stays pinned'
[[ -z "$(dc ps -q gateway)" || "$(docker inspect -f '{{.State.Running}}' "$(dc ps -aq gateway)")" == false ]] || fail 'held: gateway stopped'
if lonora update v2 >"$work/held.log" 2>&1; then fail 'update ignored the held rollback'; fi
grep -q 'A rollback is held' "$work/held.log" || fail 'held refusal'
status=0; lonora rollback >"$work/rb.log" 2>&1 || status=$?
[[ "$status" == 2 ]] || fail 'rollback without --force still holds'
lonora rollback --force >"$work/rbforce.log" 2>&1 || { show "$work/rbforce.log"; fail 'rollback --force'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'forced rollback pins v2'
[[ "$(sql "SELECT count(*) FROM ln_trading_journal WHERE operation_id='op-during-gate'")" == 0 ]] || fail 'forced rollback restored the backup'
[[ "$(sql 'SELECT version_num FROM lonora_v2_alembic')" == "$base_head" ]] || fail 'forced rollback schema'
ready || fail 'ready after forced rollback'
ok 'journal written during the gate: rollback held (DB kept, gateway stopped, commands shown); --force restores on request'

# 12. An update interrupted mid-way is rolled back by the next run, which then completes.
setsid "$home/infra/compose/lonora" update v4-good >"$work/killed.log" 2>&1 &
victim=$!
until grep -q '^phase=api' "$home/state/update-in-progress" 2>/dev/null; do
    kill -0 "$victim" 2>/dev/null || { show "$work/killed.log"; fail 'update ended before the api phase'; }
    sleep 0.5
done
kill -9 -- "-$victim"; wait "$victim" 2>/dev/null || true
[[ -f "$home/state/update-in-progress" ]] || fail 'marker survives the interruption'
lonora status >"$work/st.log" 2>&1 || true
grep -q 'UPDATE NOT FINISHED' "$work/st.log" || fail 'status shows the unfinished update'
if lonora start >"$work/start.log" 2>&1; then fail 'start ignored the unfinished update'; fi
lonora update v4-good >"$work/resume.log" 2>&1 || { show "$work/resume.log"; fail 'resumed update'; }
grep -q 'did not finish; rolling it back first' "$work/resume.log" || fail 'resume rolled back first'
grep -q 'Rolled back to' "$work/resume.log" || fail 'resume rollback result'
[[ "$(pinned)" == "$(digest_of v4-good)" ]] || fail 'resumed update pins v4-good'
[[ "$(sql 'SELECT version_num FROM lonora_v2_alembic')" == 9998_good_probe ]] || fail 'resumed update migrated'
[[ "$(owners)" == 1 ]] || fail 'data across interrupted update'
no_leftovers 'after the killed update'
ok 'interrupted update (killed in the API phase): marker kept, start refused, next update rolled back then completed'

# 13. Restoring an older backup takes a safety backup and migrates it to the image's head.
count="$(backups)"
dc exec -T api sh -c 'rm /app/.runtime/artifacts/probe.txt'
lonora restore "$b1" --replace >"$work/restore.log" 2>&1 || { show "$work/restore.log"; fail restore; }
grep -q 'Backing up the current state first' "$work/restore.log" || fail 'restore safety backup'
[[ "$(backups)" -gt "$count" ]] || fail 'safety backup written'
[[ "$(sql 'SELECT version_num FROM lonora_v2_alembic')" == 9998_good_probe ]] || fail 'restored base-head backup migrated to 9998'
[[ "$(owners)" == 1 ]] || fail 'restore brought the owner back'
dc exec -T api cat /app/.runtime/artifacts/probe.txt | grep -q lifecycle-probe || fail 'restore brought the artifact back'
if lonora restore "$b1" >/dev/null 2>&1; then fail 'restore without --replace accepted'; fi
ready || fail 'ready after restore'
no_leftovers restore
ok 'restore --replace: safety backup first, older backup migrated to the image head, data and artifacts back'

# 14. Disaster recovery on a new server: a newer backup is refused; then --with-config
# brings back the secrets while the new database password is kept.
lonora backup >/dev/null 2>&1
b4="$(ls -1t "$home"/backups/lonora-*.tar.gpg | head -n 1)"
cp "$b4" "$home/backup.key" "$work/"
wipe
install_fresh v2
install -m 600 "$work/backup.key" "$home/backup.key"
if lonora restore "$work/$(basename "$b4")" --replace >"$work/newer.log" 2>&1; then fail 'newer backup restored onto an older image'; fi
grep -q 'which the installed image does not know' "$work/newer.log" || { show "$work/newer.log"; fail 'newer-backup refusal'; }
wipe
install_fresh v4-good
new_password="$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")"
install -m 600 "$work/backup.key" "$home/backup.key"
lonora restore "$work/$(basename "$b4")" --replace --with-config >"$work/dr.log" 2>&1 || { show "$work/dr.log"; fail 'disaster recovery'; }
[[ "$(sed -n 's/^LONORA_ENCRYPTION_KEY=//p' "$home/.env")" == "$key" ]] || fail 'DR restored the encryption key'
[[ "$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")" == "$new_password" ]] || fail 'DR kept the new database password'
[[ "$(stat -c %a "$home/.env")" == 600 ]] || fail 'DR .env mode'
[[ "$(owners)" == 1 ]] || fail 'DR brought the owner back'
ready || fail 'ready after DR'
for secret in "$key" "$backup_key"; do
    if grep -qF -- "$secret" "$work/dr.log"; then fail 'DR printed a secret'; fi
done
ok 'disaster recovery: newer backup refused on an older image; --with-config restores secrets, keeps the new DB password, /ready'

# 15. Optional path: adopt an installation that runs an image from before this tooling.
# The old image creates its own (older) schema, as a real old installation has.
wipe
install_fresh v2
dc down -v >/dev/null 2>&1
printf 'LONORA_IMAGE=%s\n' "$(digest_of old)" >"$home/state/image.env"
dc up -d --wait >/dev/null 2>&1 || fail 'old image start'
old_rev="$(sql 'SELECT version_num FROM lonora_v2_alembic')"
lonora update v2 >"$work/adopt.log" 2>&1 || { show "$work/adopt.log"; fail 'adopt old install'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'adoption pins v2'
[[ "$(sql 'SELECT version_num FROM lonora_v2_alembic')" == "$base_head" ]] || fail "adoption migrated $old_rev to $base_head"
ok "adoption (optional): an old-image installation at $old_rev updates to v2 at $base_head"

printf '\nAll %d lifecycle checks passed.\n' "$passed"
