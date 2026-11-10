#!/usr/bin/env bash
# End-to-end test of the production lifecycle against real Docker (docs/operations.md,
# "Testing"). Each review finding of PR #43 has a check here.
#
#   bash tests/ops/lifecycle_test.sh REPO
#
# REPO is a registry repository holding these tags; tests/ops/build_test_images.sh REPO
# builds and pushes all six:
#   old        an image built from a commit before this tooling (no bundle, no manifest)
#   v1, v2     two builds of this tree with different LONORA_VERSION build args
#   v4-good    v2 + a working migration (9998_good_probe)
#   v3-broken  v4-good + a schema-changing migration (9999) and a Gateway that never starts
#   v3-fixed   v3-broken's migrations with a working Gateway
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
revision() { sql 'SELECT version_num FROM lonora_v2_alembic'; }
pinned() { sed -n 's/^LONORA_IMAGE=//p' "$home/state/image.env"; }
digest_of() { docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$repo:$1" | grep -m1 "^$repo@"; }
owners() { sql "SELECT count(*) FROM ln_owners"; }
phase() { sed -n 's/^phase=//p' "$home/state/update-in-progress" 2>/dev/null || true; }
gateway_running() { [[ -n "$(dc ps -q gateway)" ]]; }
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
    if [[ -n "$(find "$home/backups" -mindepth 1 \( -name '.work*' -o -name '*.part' \) -print)" ]]; then fail "$1: scratch files in backups/"; fi
    if [[ -n "$(find "$home/state/.work" -mindepth 1 -print 2>/dev/null)" ]]; then fail "$1: scratch files left in state/.work"; fi
    if [[ -n "$(find "$home" -maxdepth 1 -name '.env.merge.*')" ]]; then fail "$1: merge files left"; fi
    if [[ -n "$(find /tmp -maxdepth 1 -name 'lonora-gpg.*' -print)" ]]; then fail "$1: gpg homes left in /tmp"; fi
}
post_status() { # HTTP status of a write through Caddy (the owner's path)
    curl -sk -o "$work/post.body" -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' https://localhost/api/onboarding || true
}
wait_phase() { # $1 phase, $2 pid of the update
    until [[ "$(phase)" == "$1" ]]; do
        kill -0 "$2" 2>/dev/null || return 1
        sleep 0.5
    done
}
install_fresh() { # $1 version
    LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$home" --domain localhost --version "$1" --no-systemd >"$work/install-$1.log" 2>&1 || { show "$work/install-$1.log"; fail "install $1"; }
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
db_wrapper() { # $1 binary in the db container, $2 shell body that runs before the real one
    dc exec -T db sh -c "mv /usr/local/bin/$1 /usr/local/bin/$1.real && printf '#!/bin/sh\n%s\nexec /usr/local/bin/$1.real \"\$@\"\n' '$2' >/usr/local/bin/$1 && chmod 755 /usr/local/bin/$1"
}
db_unwrap() { dc exec -T db sh -c "mv -f /usr/local/bin/$1.real /usr/local/bin/$1"; }

# 1. Install with no toolchain beyond Docker and gpg.
install_fresh v1
[[ "$(pinned)" == "$(digest_of v1)" ]] || fail 'install pins the v1 digest'
[[ "$(stat -c %a "$home/.env")" == 600 && "$(stat -c %a "$home/backup.key")" == 600 ]] || fail 'secret file modes'
[[ "$(stat -c %a "$home/infra/compose/Caddyfile.prod")" == 644 && "$(stat -c %a "$home/infra/compose/lonora")" == 755 ]] || fail 'bundle file modes'
key="$(sed -n 's/^LONORA_ENCRYPTION_KEY=//p' "$home/.env")"
backup_key="$(cat "$home/backup.key")"
first_password="$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")"
bootstrap="$(sed -n 's/^LONORA_BOOTSTRAP_TOKEN=//p' "$home/.env")"
webhook="$(sed -n 's/^LONORA_WEBHOOK_SECRET=//p' "$home/.env")"
new_password=""
if LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$home" --domain localhost --version v1 --no-systemd >"$work/reinstall.log" 2>&1; then fail 'installer ran over an installation'; fi
grep -q 'already has an installation' "$work/reinstall.log" || fail 'reinstall refusal message'
if LONORA_INSTALL_ALLOW_NON_ROOT=1 bash "$root/infra/compose/install.sh" --home "$work/other" --domain localhost --version v1 --no-systemd >"$work/othervolume.log" 2>&1; then fail 'installer reused the existing lonora_database volume'; fi
grep -q 'lonora_database already exists' "$work/othervolume.log" || fail 'volume guard message'
[[ ! -e "$work/other/.env" ]] || fail 'volume guard wrote a second installation'
ok 'install: digest pinned, /ready, secrets 600, bundle modes 644/755; refuses its own home and a leftover lonora_database volume'

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
[[ ! -e "$work/bundle/infra/compose/deploy-main.sh" && ! -e "$work/bundle/infra/compose/docker-compose.postgres-host.yml" ]] || fail 'legacy deployment paths still shipped'
ok 'image bundle and release.json: no secret files or values, no legacy deployment paths'

# 3. Seed real state: the owner account and one artifact file.
dc exec -T api python -c "import json,os,urllib.request
body=json.dumps({'email':'owner@example.com','password':'lifecycle-test-password-1','bootstrap_token':os.environ['LONORA_BOOTSTRAP_TOKEN']}).encode()
urllib.request.urlopen(urllib.request.Request('http://localhost:8000/api/onboarding',body,{'Content-Type':'application/json'}),timeout=10)" >/dev/null
dc exec -T api sh -c 'echo lifecycle-probe >/app/.runtime/artifacts/probe.txt'
[[ "$(owners)" == 1 ]] || fail 'seed owner'
owner_id="$(sql 'SELECT id FROM ln_owners LIMIT 1')"
ok 'seed: owner account and artifact'

# 4. Encrypted, verified backup; the plaintext markers exist only after decryption.
lonora backup >"$work/backup.log" 2>&1 || { show "$work/backup.log"; fail backup; }
b1="$(ls -1t "$home"/backups/lonora-*.tar.gpg | head -n 1)"
[[ "$(stat -c %a "$b1")" == 600 ]] || fail 'backup mode'
if tar -tf "$b1" >/dev/null 2>&1; then fail 'the backup file is a readable tar'; fi
gpg_key --decrypt --output "$work/b1.tar" "$b1"
mkdir "$work/b1" && tar -C "$work/b1" -xf "$work/b1.tar"
grep -qa PGDMP "$work/b1/database.dump" || fail 'positive control: the decrypted dump is a pg_dump'
grep -qaF -- "$key" <(tar -xzOf "$work/b1/config.tar.gz" .env) || fail 'positive control: the decrypted config holds .env'
if grep -qa PGDMP "$b1"; then fail 'backup holds a clear database dump'; fi
if grep -qaF -- "$key" "$b1"; then fail 'backup holds the encryption key in clear'; fi
if grep -qaF -- lifecycle-probe "$b1"; then fail 'backup holds clear artifacts'; fi
if tar -tzf "$work/b1/config.tar.gz" | grep -q '^infra'; then fail 'backup carries deployment files'; fi
no_leftovers backup
ok 'backup: verified, encrypted (not a readable tar; decrypted copy has the dump and .env, the file has neither), no deployment files'

# 5. Restore test: isolated network verified, no container or volume left behind.
volumes_before="$(docker volume ls -q | wc -l)"
lonora restore-test "$b1" >"$work/rt.log" 2>&1 || { show "$work/rt.log"; fail restore-test; }
grep -q 'Network isolation verified: internal network, no route out' "$work/rt.log" || fail 'restore-test network isolation check'
grep -q 'Restore test passed' "$work/rt.log" || fail 'restore-test verdict'
[[ -z "$(docker ps -aq --filter name=lonora-restoretest)" ]] || fail 'restore-test left containers'
[[ -z "$(docker network ls -q --filter name=lonora-restoretest)" ]] || fail 'restore-test left its network'
[[ "$(docker volume ls -q | wc -l)" == "$volumes_before" ]] || fail 'restore-test left a volume with the restored data'
no_leftovers restore-test
ok "restore-test: internal network with no route out, then $(sed -n 's/^lonora: Restore test passed: //p' "$work/rt.log")"

# 6. Damaged, wrong-key and forged (unencrypted) backups are refused.
cp "$b1" "$work/damaged.tar.gpg"
printf 'X' | dd of="$work/damaged.tar.gpg" bs=1 seek=$(($(stat -c %s "$b1") / 2)) conv=notrunc status=none
if lonora restore-test "$work/damaged.tar.gpg" >"$work/damaged.log" 2>&1; then fail 'damaged backup accepted'; fi
grep -q 'Decryption failed' "$work/damaged.log" || fail 'damaged backup refused for the wrong reason'
if LONORA_BACKUP_KEY=wrong-key lonora restore-test "$b1" >"$work/wrongkey.log" 2>&1; then fail 'wrong key accepted'; fi
grep -q 'Decryption failed' "$work/wrongkey.log" || fail 'wrong key refused for the wrong reason'
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
for mode in 1 0; do
    count="$(backups)"
    dc exec -T db sh -c "mv /usr/local/bin/pg_dump /usr/local/bin/pg_dump.real && printf '#!/bin/sh\n/usr/local/bin/pg_dump.real \"\$@\" | head -c 4000\nexit $mode\n' >/usr/local/bin/pg_dump && chmod 755 /usr/local/bin/pg_dump"
    if lonora update v2 >"$work/dumpfail-$mode.log" 2>&1; then fail "update succeeded with a broken pg_dump (exit $mode)"; fi
    db_unwrap pg_dump
    grep -q 'Backup failed; nothing was changed' "$work/dumpfail-$mode.log" || { show "$work/dumpfail-$mode.log"; fail "pg_dump exit $mode: abort message"; }
    [[ "$(pinned)" == "$(digest_of v1)" ]] || fail "pg_dump exit $mode: pin changed"
    [[ ! -e "$home/state/update-in-progress" && ! -e "$home/maintenance/on" ]] || fail "pg_dump exit $mode: marker or maintenance left"
    [[ "$(backups)" == "$count" ]] || fail "pg_dump exit $mode: a bad backup was kept"
    [[ "$(owners)" == 1 ]] || fail "pg_dump exit $mode: live data changed"
    ready || fail "pg_dump exit $mode: services not back"
    no_leftovers "pg_dump exit $mode"
done
ok 'failed pg_dump (exit 1) and truncated pg_dump (exit 0): update aborted before pinning, live DB untouched, no bad backup kept'

# 8. Refusals that change nothing: concurrent operation, no pin, a tag pin, no manifest.
exec 8>"$home/state/lock"
flock 8
if lonora update v2 >"$work/locked.log" 2>&1; then fail 'update ran while locked'; fi
grep -q 'Another lonora operation' "$work/locked.log" || fail 'lock message'
exec 8>&-
cp "$home/state/image.env" "$work/image.env.saved"
rm "$home/state/image.env"
if lonora update v2 >"$work/nopin.log" 2>&1; then fail 'update ran without a pin'; fi
grep -q 'No pinned image' "$work/nopin.log" || fail 'no-pin message'
printf 'LONORA_IMAGE=%s:v1\n' "$repo" >"$home/state/image.env"
if lonora update v2 >"$work/tagpin.log" 2>&1; then fail 'update ran from a tag pin'; fi
grep -q 'is not a repo@sha256 digest' "$work/tagpin.log" || fail 'tag-pin message'
cp "$work/image.env.saved" "$home/state/image.env"
if lonora update old >"$work/old.log" 2>&1; then fail 'manifest-less image accepted'; fi
grep -q 'no release manifest' "$work/old.log" || fail 'manifest refusal message'
ready || fail 'services after refusals'
ok 'refused without change: a concurrent operation, no pin, a tag (not digest) pin, an image without a release manifest'

# 9. Update to v2; the running script is replaced by rename; writes work again afterwards.
inode_before="$(stat -c %i "$home/infra/compose/lonora")"
lonora update v2 >"$work/update.log" 2>&1 || { show "$work/update.log"; fail 'update v2'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'update pins the v2 digest'
[[ "$(owners)" == 1 ]] || fail 'data kept across update'
grep -q 'Backup taken first' "$work/update.log" || fail 'update took a backup'
grep -q 'Starting the API; the Gateway stays stopped' "$work/update.log" || fail 'API gated before the Gateway'
[[ "$(stat -c %i "$home/infra/compose/lonora")" != "$inode_before" ]] || fail 'script rewritten in place'
[[ ! -e "$home/maintenance/on" ]] || fail 'maintenance left on after a successful update'
[[ "$(post_status)" != 503 ]] || fail 'writes still refused after the update'
ok 'update v2: backup first, migrate step, API then Gateway, /ready, digest pinned, script replaced atomically, writes open again'

# 10. A failing update with no owner or money writes rolls back image and schema; while it
# runs, Caddy refuses writes with the maintenance answer.
dc exec -T db psql -U lonora -d lonora -qc "CREATE TABLE ops_probe (note text); INSERT INTO ops_probe VALUES ('before-update')" >/dev/null
lonora update v3-broken >"$work/broken.log" 2>&1 &
updater=$!
wait_phase gateway "$updater" || { show "$work/broken.log"; fail 'broken update ended before the gateway phase'; }
code="$(post_status)"
[[ "$code" == 503 ]] || fail "write during the update answered $code, not 503"
grep -q 'يجري التحديث' "$work/post.body" || fail 'maintenance answer text'
status=0; wait "$updater" || status=$?
[[ "$status" == 1 ]] || { show "$work/broken.log"; fail "broken update exit status $status"; }
grep -q 'Rolling back (/ready health gate)' "$work/broken.log" || { show "$work/broken.log"; fail 'failure point'; }
grep -q 'Rolled back to' "$work/broken.log" || { show "$work/broken.log"; fail 'rollback message'; }
[[ "$(pinned)" == "$(digest_of v2)" ]] || fail 'rollback restores the v2 pin'
[[ "$(revision)" == "$base_head" ]] || fail 'rollback restores the schema revision'
[[ "$(sql "SELECT to_regclass('ln_broken_probe') IS NULL")" == t ]] || fail 'rollback removed the broken migration table'
[[ "$(sql "SELECT string_agg(note, ',') FROM ops_probe")" == before-update ]] || fail 'rows written before the update survive'
[[ ! -e "$home/maintenance/on" ]] || fail 'maintenance left on after the rollback'
ready || fail 'ready after rollback'
no_leftovers rollback
ok 'broken update: writes answered 503 «يجري التحديث» during it; restored from the pre-update backup (no downgrade), earlier rows kept'

# 10b. The rollback's restore fails after DROP DATABASE: it stops with a command that
# works, and that command retries the restore.
lonora update v3-broken >"$work/broken2.log" 2>&1 &
updater=$!
wait_phase gateway "$updater" || { show "$work/broken2.log"; fail 'second broken update ended early'; }
db_wrapper pg_restore 'if [ -f /tmp/fail-once ]; then rm -f /tmp/fail-once; cat >/dev/null; exit 1; fi'
dc exec -T db touch /tmp/fail-once
status=0; wait "$updater" || status=$?
[[ "$status" == 1 ]] || { show "$work/broken2.log"; fail "incomplete rollback exit status $status"; }
grep -q 'ROLLBACK INCOMPLETE' "$work/broken2.log" || { show "$work/broken2.log"; fail 'incomplete rollback message'; }
grep -q 'sudo lonora rollback' "$work/broken2.log" || fail 'incomplete rollback names the next command'
[[ "$(phase)" == restoring ]] || fail "marker phase after the failed restore: $(phase)"
lonora rollback >"$work/retry.log" 2>&1 || { show "$work/retry.log"; fail 'rollback retry'; }
db_unwrap pg_restore
grep -q 'Rolled back to' "$work/retry.log" || fail 'retry result'
if grep -q 'HELD' "$work/retry.log"; then fail 'retry misreported a hold'; fi
[[ "$(pinned)" == "$(digest_of v2)" && "$(revision)" == "$base_head" && "$(owners)" == 1 ]] || fail 'state after the retried restore'
ready || fail 'ready after the retried restore'
ok 'restore failing after DROP: rollback stops at phase restoring with a working command; lonora rollback retries and completes'

# 12. An update interrupted mid-way is rolled back by the next run, which then completes.
setsid "$home/infra/compose/lonora" update v4-good >"$work/killed.log" 2>&1 &
victim=$!
wait_phase api "$victim" || { show "$work/killed.log"; fail 'update ended before the api phase'; }
kill -9 -- "-$victim"; wait "$victim" 2>/dev/null || true
[[ -f "$home/state/update-in-progress" ]] || fail 'marker survives the interruption'
lonora status >"$work/st.log" 2>&1 || true
grep -q 'UPDATE NOT FINISHED' "$work/st.log" || fail 'status shows the unfinished update'
if lonora start >"$work/start.log" 2>&1; then fail 'start ignored the unfinished update'; fi
lonora update v4-good >"$work/resume.log" 2>&1 || { show "$work/resume.log"; fail 'resumed update'; }
grep -q 'did not finish; rolling it back first' "$work/resume.log" || fail 'resume rolled back first'
grep -q 'Rolled back to' "$work/resume.log" || fail 'resume rollback result'
[[ "$(pinned)" == "$(digest_of v4-good)" && "$(revision)" == 9998_good_probe && "$(owners)" == 1 ]] || fail 'state after the resumed update'
no_leftovers 'after the killed update'
ok 'interrupted update (killed in the API phase): marker kept, start refused, next update rolled back then completed'

# 13. Restore, from another directory, with the db stopped, of the oldest backup while
# rotation would delete it: safety backup first, file kept, older schema migrated up.
dc exec -T api sh -c 'rm /app/.runtime/artifacts/probe.txt'
dc stop db >/dev/null 2>&1
count="$(backups)"
(cd / && LONORA_BACKUP_KEEP="$count" "$home/infra/compose/lonora" restore "backups/$(basename "$b1")" --replace) >"$work/restore.log" 2>&1 || { show "$work/restore.log"; fail restore; }
grep -q 'Backing up the current state first' "$work/restore.log" || fail 'restore safety backup with the db stopped'
[[ -f "$b1" ]] || fail 'rotation deleted the backup being restored'
[[ "$(revision)" == 9998_good_probe ]] || fail 'restored base-head backup migrated to 9998'
[[ "$(owners)" == 1 ]] || fail 'restore brought the owner back'
dc exec -T api cat /app/.runtime/artifacts/probe.txt | grep -q lifecycle-probe || fail 'restore brought the artifact back'
if lonora restore "$b1" >/dev/null 2>&1; then fail 'restore without --replace accepted'; fi
ready || fail 'ready after restore'
no_leftovers restore
ok 'restore (relative path from /, db stopped, oldest of KEEP): db started, safety backup, file not rotated, migrated to the image head'

# 11. An owner-control write while the new version runs holds the rollback; --keep-data
# with the same digest or a bad tag keeps it held; a fixed version updates forward.
lonora update v3-broken >"$work/hold.log" 2>&1 &
updater=$!
wait_phase gateway "$updater" || { show "$work/hold.log"; fail 'hold update ended early'; }
dc exec -T db psql -U lonora -d lonora -qc "INSERT INTO ln_trading_restrictions (id, owner_id, account_id, symbol_verified, action_class, valid_from, source, reason, created_by, applies_to_owner_manual, created_at, updated_at) VALUES ('r-during-gate', '$owner_id', 'acct', true, 'no_new_entries', now(), 'owner_ui', 'test', 'owner', false, now(), now())" >/dev/null
status=0; wait "$updater" || status=$?
[[ "$status" == 2 ]] || { show "$work/hold.log"; fail "restriction hold exit status ($status)"; }
grep -q 'ROLLBACK HELD: owner controls' "$work/hold.log" || { show "$work/hold.log"; fail 'restriction hold reason'; }
[[ "$(phase)" == hold && -e "$home/maintenance/on" ]] || fail 'held: marker phase and maintenance'
if gateway_running; then fail 'held: gateway still running'; fi
# (a) the same failed digest: started behind the gates, still fails, still held
status=0; lonora update v3-broken --keep-data >"$work/keep-same.log" 2>&1 || status=$?
[[ "$status" == 2 ]] || { show "$work/keep-same.log"; fail "keep-data same digest exit $status"; }
grep -q 'already pinned; starting it behind the health gates' "$work/keep-same.log" || fail 'same digest is started, not "Already on"'
[[ "$(phase)" == hold && -f "$home/state/rollback-bundle.tar.gz" ]] || fail 'keep-data same digest: still held'
if gateway_running; then fail 'keep-data same digest: gateway stopped again'; fi
# (b) a bad tag: refused before anything changes
if lonora update no-such-tag --keep-data >"$work/keep-bad.log" 2>&1; then fail 'keep-data with a bad tag succeeded'; fi
grep -q 'Cannot pull' "$work/keep-bad.log" || fail 'bad tag message'
[[ "$(phase)" == hold && -f "$home/state/rollback-bundle.tar.gz" && ! -e "$home/state/held-update" ]] || fail 'bad tag: hold intact'
# (c) a fixed version: forward update keeps the data, closes the hold
lonora update v3-fixed --keep-data >"$work/keep-fixed.log" 2>&1 || { show "$work/keep-fixed.log"; fail 'keep-data forward update'; }
[[ "$(pinned)" == "$(digest_of v3-fixed)" && "$(revision)" == 9999_broken_probe ]] || fail 'forward update state'
[[ "$(sql "SELECT count(*) FROM ln_trading_restrictions WHERE id='r-during-gate'")" == 1 ]] || fail 'forward update kept the restriction'
[[ ! -e "$home/state/update-in-progress" && ! -e "$home/state/held-update" && ! -e "$home/maintenance/on" ]] || fail 'forward update closed the hold'
ready || fail 'ready after forward update'
ok 'restriction written during the gate: held; --keep-data same digest stays held, bad tag changes nothing, fixed version updates forward keeping it'

# 11b. A trading-journal write holds too; timer backups during the hold never rotate its
# backup away; rollback without --force still holds; --force restores on request.
lonora update v3-broken >"$work/money.log" 2>&1 &
updater=$!
wait_phase gateway "$updater" || { show "$work/money.log"; fail 'money update ended early'; }
dc exec -T db psql -U lonora -d lonora -qc "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id, request_hash, request, status, result, submitted_at, updated_at) VALUES ('op-during-gate', '$owner_id', 'acct', 'h', '{}', 'submitted', '{}', now(), now())" >/dev/null
status=0; wait "$updater" || status=$?
[[ "$status" == 2 ]] || { show "$work/money.log"; fail "journal hold exit status ($status)"; }
held_backup="$(sed -n 's/^backup=//p' "$home/state/update-in-progress")"
for _ in 1 2 3; do LONORA_BACKUP_KEEP=1 lonora backup >>"$work/hold-backups.log" 2>&1 || { show "$work/hold-backups.log"; fail 'backup during hold'; }; done
[[ -f "$held_backup" ]] || fail 'rotation deleted the held update backup'
status=0; lonora rollback >"$work/rb.log" 2>&1 || status=$?
[[ "$status" == 2 ]] || fail 'rollback without --force still holds'
lonora rollback --force >"$work/rbforce.log" 2>&1 || { show "$work/rbforce.log"; fail 'rollback --force'; }
[[ "$(pinned)" == "$(digest_of v3-fixed)" ]] || fail 'forced rollback pins v3-fixed'
[[ "$(sql "SELECT count(*) FROM ln_trading_journal WHERE operation_id='op-during-gate'")" == 0 ]] || fail 'forced rollback restored the backup'
[[ ! -e "$home/maintenance/on" ]] || fail 'maintenance off after the forced rollback'
ready || fail 'ready after forced rollback'
ok 'journal written during the gate: held; backups during the hold keep its backup; rollback holds; --force restores on request'

# 14. Disaster recovery on a new server: a newer backup is refused; then --with-config
# brings back the secrets while the new database password is kept.
lonora backup >"$work/backup-dr.log" 2>&1
b4="$(ls -1t "$home"/backups/lonora-*.tar.gpg | head -n 1)"
cp "$b4" "$work/"
cp "$home/state/history.log" "$work/history-1.log"
install -m 600 "$home/backup.key" "$work/backup.key"
wipe
install_fresh v2
install -m 600 "$work/backup.key" "$home/backup.key"
if lonora restore "$work/$(basename "$b4")" --replace >"$work/newer.log" 2>&1; then fail 'newer backup restored onto an older image'; fi
grep -q 'which the installed image does not know' "$work/newer.log" || { show "$work/newer.log"; fail 'newer-backup refusal'; }
wipe
install_fresh v3-fixed
new_password="$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")"
install -m 600 "$work/backup.key" "$home/backup.key"
lonora restore "$work/$(basename "$b4")" --replace --with-config >"$work/dr.log" 2>&1 || { show "$work/dr.log"; fail 'disaster recovery'; }
[[ "$(sed -n 's/^LONORA_ENCRYPTION_KEY=//p' "$home/.env")" == "$key" ]] || fail 'DR restored the encryption key'
[[ "$(sed -n 's/^LONORA_POSTGRES_PASSWORD=//p' "$home/.env")" == "$new_password" ]] || fail 'DR kept the new database password'
[[ "$(stat -c %a "$home/.env")" == 600 ]] || fail 'DR .env mode'
[[ "$(owners)" == 1 ]] || fail 'DR brought the owner back'
ready || fail 'ready after DR'
cp "$home/state/history.log" "$work/history-2.log" 2>/dev/null || true
ok 'disaster recovery: newer backup refused on an older image; --with-config restores secrets, keeps the new DB password, /ready'

# 15. No secret in anything the tooling printed or logged.
for secret in "$key" "$backup_key" "$first_password" "$new_password" "$bootstrap" "$webhook"; do
    [[ -n "$secret" ]] || continue
    leak="$(grep -lF -- "$secret" "$work"/*.log 2>/dev/null | head -n 1 || true)"
    [[ -z "$leak" ]] || fail "a secret appears in $leak"
done
ok "no secret (encryption key, backup key, DB passwords, bootstrap token, webhook secret) in $(find "$work" -maxdepth 1 -name '*.log' | wc -l) logs and history files"

printf '\nAll %d lifecycle checks passed.\n' "$passed"
