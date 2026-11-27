#!/usr/bin/env bash
# The Lonora Cloud host (docs/cloud/DECISIONS.md D48): one server, every customer's own installation.
#
#   customer.sh [--dry-run] init                    shared services, the website, its sudo rule
#   customer.sh [--dry-run] release <git-ref>       build the release image once, switch every customer
#   customer.sh [--dry-run] create <handle> [--owner-on-stdin]   a customer's database, keys, Lonora and route
#   customer.sh [--dry-run] update <handle>         one customer onto the current release image
#   customer.sh [--dry-run] remove <handle>         everything of that customer, its data included
#   customer.sh [--dry-run] workspace <handle> start|stop   its workspace and browser, on demand
#   customer.sh [--dry-run] backup                  the databases and every key, kept 7 nights (lonora-backup.timer)
#
# create --owner-on-stdin (the site) reads the website account that asked for it on stdin (its email,
# then its password hash, one per line) and makes it the owner, so the customer signs in with the
# password they signed up with; it then prints one line on stdout, instance_url=https://<handle>.<BASE_DOMAIN>/.
# Run by hand without it, create prints setup_link=https://<handle>.<BASE_DOMAIN>/#token=… instead.
# Progress goes to stderr and never holds a secret: the database password and the encryption key
# exist only in the customer's env file (mode 600). --dry-run prints every Docker and system command
# instead of running it; files are still written under LONORA_HOST_HOME (use a scratch folder).
# Settings: /srv/lonora/host.env (BASE_DOMAIN, SITE_DOMAIN, ACME_EMAIL; init adds POSTGRES_PASSWORD).
set -euo pipefail
umask 077

DRY=false
if [[ "${1:-}" == --dry-run ]]; then DRY=true; shift; fi
HOME_DIR="${LONORA_HOST_HOME:-/srv/lonora}"
HOST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO=https://github.com/loorksy/lonorabot.git
say() { printf 'customer: %s\n' "$*" >&2; }
die() { say "$*"; exit 1; }
refuse() { say "$*"; exit 73; } # exit 73: nothing was changed, so the site has nothing to undo
run() { if $DRY; then say "would run: $*"; else "$@"; fi; }
run_in() { if $DRY; then cat >/dev/null; fi; run "$@"; } # the same, for a command that reads stdin
secret() { head -c "$1" /dev/urandom | base64 | tr -d '\n=' | tr '+/' '-_'; }
[[ -f "$HOME_DIR/host.env" ]] || die "Write $HOME_DIR/host.env first (cloud/site/README.md)."
# shellcheck source=/dev/null
. "$HOME_DIR/host.env"
: "${BASE_DOMAIN:?set BASE_DOMAIN in host.env}"
mkdir -p "$HOME_DIR/customers" "$HOME_DIR/caddy/customers"
# One change to the host at a time. release takes it only after its build, so activations go on meanwhile.
lock() { exec 9>"$HOME_DIR/.lock"; flock -w "$1" 9 || refuse 'Busy: another customer.sh command (a release?) is running; try again shortly.'; }

customer() { # $1 handle: the names of one customer
    [[ "$1" =~ ^[a-z][a-z0-9-]{1,28}[a-z0-9]$ && "$1" != *--* ]] || die "Not a valid handle: $1"
    handle="$1" dir="$HOME_DIR/customers/$1" project="lonora-$1" db="lonora_${1//-/_}" domain="$1.$BASE_DOMAIN"
}
compose() { run docker compose -f "$HOST/customer.yml" --project-directory "$dir" --env-file "$dir/.env" --env-file "$HOME_DIR/release.env" --profile on-demand "$@"; }
psql_admin() { run_in docker exec -i lonora-postgres psql -q -v ON_ERROR_STOP=1 -v VERBOSITY=terse -U postgres; }
reload_proxy() { run docker exec lonora-caddy caddy reload --config /etc/caddy/Caddyfile; }
# Every global address of this host: the customer's workspace may reach none of them.
host_addresses() { { ip -o addr show scope global 2>/dev/null | awk '{print $4}' | sed 's#/.*##'; hostname -I 2>/dev/null | tr ' ' '\n'; } | grep -E '^[0-9a-fA-F:.]+$' | sort -u | tr '\n' ' ' || true; }

create() {
    [[ ! -e "$dir" ]] || refuse "$handle already exists; choose another handle."
    [[ -s "$HOME_DIR/release.env" ]] || die "No release yet: run customer.sh release <git-ref>."
    local password token owner=""
    [[ "${1:-}" != --owner-on-stdin ]] || owner="$(head -c 512)"
    [[ -z "$owner" || "$owner" =~ ^[^[:space:]@]+@[^[:space:]@]+$'\n'pbkdf2-sha256\$[0-9]+\$[0-9a-f]+\$[0-9a-f]{64}$'\n'?$ ]] ||
        refuse "The owner on stdin is not an email and a website password hash."
    password="$(secret 24)" token="$(secret 32)"
    mkdir -p "$dir/workspace"
    cat >"$dir/.env" <<EOF
LONORA_PROJECT=$project
LONORA_DOMAIN=$domain
LONORA_ALLOWED_ORIGIN=https://$domain
LONORA_DATABASE_URL=postgresql+asyncpg://$db:$password@lonora-postgres:5432/$db
LONORA_ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')
LONORA_BOOTSTRAP_TOKEN=$token
LONORA_WEBHOOK_SECRET=$(secret 32)
LONORA_CHART_RENDERER_URL=http://$project-api:8000/charts/render
LONORA_WORKSPACE_HOST_ADDRESSES=$(host_addresses)
EOF
    say "Creating the database and role $db."
    printf 'CREATE ROLE "%s" LOGIN PASSWORD '\''%s'\'';\nCREATE DATABASE "%s" OWNER "%s";\nREVOKE ALL ON DATABASE "%s" FROM PUBLIC;\n' \
        "$db" "$password" "$db" "$db" "$db" | psql_admin
    say "Creating the workspace disk (${WORKSPACE_DISK:-10g})."
    run fallocate -l "${WORKSPACE_DISK:-10g}" "$dir/workspace.img"
    run mkfs.ext4 -q -F -m 0 "$dir/workspace.img"
    printf '%s %s ext4 loop,nodev,nosuid,nofail 0 0\n' "$dir/workspace.img" "$dir/workspace" | run_in tee -a /etc/fstab >/dev/null
    run mount "$dir/workspace"
    run touch "$dir/workspace/.lonora-workspace-disk"
    say "Starting Lonora for $domain."
    compose up -d --wait --wait-timeout 240 api gateway
    if [[ -n "$owner" ]]; then
        say "Making the website account the owner of this Lonora."
        compose exec -T api lonora-api --import-owner <<<"$owner"
    fi
    printf '%s {\n\timport customer %s-api\n}\n' "$domain" "$project" >"$HOME_DIR/caddy/customers/$handle.caddy"
    chmod 644 "$HOME_DIR/caddy/customers/$handle.caddy"
    reload_proxy
    if ! $DRY; then # the site stops waiting at 300 s
        until curl -fs -m 5 -o /dev/null "https://$domain/ready"; do ((SECONDS < 270)) || die "https://$domain/ready did not answer."; sleep 2; done
    fi
    say "Ready: https://$domain"
    if [[ -n "$owner" ]]; then printf 'instance_url=https://%s/\n' "$domain"; else printf 'setup_link=https://%s/#token=%s\n' "$domain" "$token"; fi
}

update() {
    [[ -f "$dir/.env" ]] || die "No customer $handle."
    local running
    running="$(compose ps --services --status running | grep -E '^(workspace-net|workspace|browser)$' | tr '\n' ' ' || true)"
    # shellcheck disable=SC2086 # one word per running on-demand service
    compose up -d --wait --wait-timeout 240 api gateway $running && say "$handle runs the current release."
}

remove() {
    if [[ -f "$dir/.env" ]]; then compose down --volumes --remove-orphans; fi
    rm -f "$HOME_DIR/caddy/customers/$handle.caddy"
    reload_proxy
    if mountpoint -q "$dir/workspace"; then run umount "$dir/workspace"; fi
    run sed -i "\\#^$dir/workspace.img #d" /etc/fstab
    printf 'DROP DATABASE IF EXISTS "%s" WITH (FORCE);\nDROP ROLE IF EXISTS "%s";\n' "$db" "$db" | psql_admin
    rm -rf "$dir"
    say "$handle is removed."
}

workspace() {
    [[ -f "$dir/.env" ]] || die "No customer $handle."
    case "${1:-}" in
        start)
            # Without its own disk mounted (a nofail mount that was skipped), the workspace would write
            # to the shared disk, so it does not start.
            $DRY || mountpoint -q "$dir/workspace" || die "The workspace disk of $handle is not mounted: mount $dir/workspace first."
            compose up -d workspace-net workspace browser ;;
        stop) compose stop workspace workspace-net browser ;;
        *) die 'usage: customer.sh workspace <handle> start|stop' ;;
    esac
}

release() {
    local ref="${1:?usage: customer.sh release <git-ref>}" src="$HOME_DIR/build" digest="127.0.0.1:5055/lonora@sha256:dry-run" d failed=""
    exec 8>"$HOME_DIR/.build-lock"
    flock -n 8 || die 'A release is already being built.'
    rm -rf "$src"
    run git init -q "$src"
    run git -C "$src" fetch -q --depth 1 "$SOURCE_REPO" "$ref"
    run git -C "$src" checkout -q FETCH_HEAD
    say "Building the release image once from $ref."
    if ! $DRY; then
        digest="$(bash "$src/infra/compose/build-from-source.sh" --source "$src" --project lonora-cloud --cpus 2 --memory 3g | sed -n 's/^build: Digest: //p')"
    fi
    [[ -n "$digest" ]] || die 'The build printed no digest.'
    lock 900
    printf 'LONORA_IMAGE=%s\n' "$digest" >"$HOME_DIR/release.env"
    for d in "$HOME_DIR"/customers/*/; do
        [[ -d "$d" ]] || continue
        customer "$(basename "$d")"
        update || failed+=" $handle"
    done
    [[ -z "$failed" ]] || die "Release $ref: $digest. Not switched:$failed (customer.sh update <handle>)."
    say "Release $ref: $digest"
}

# Docker's default address pools hold about 30 networks, and each customer uses two or three, so
# the host would stop taking customers after nine or ten. Once, before any customer: 256 networks.
widen_docker_pools() {
    local conf=/etc/docker/daemon.json
    grep -qs default-address-pools "$conf" && return 0
    say "Widening Docker's network pools to 10.201.0.0/16 in /24 networks; Docker restarts once."
    run python3 -c 'import json, os, sys
p = sys.argv[1]
c = json.load(open(p)) if os.path.isfile(p) and os.path.getsize(p) else {}
c["default-address-pools"] = [{"base": "10.201.0.0/16", "size": 24}]
os.makedirs(os.path.dirname(p), exist_ok=True)
open(p, "w").write(json.dumps(c, indent=2) + "\n")' "$conf"
    run systemctl restart docker
}

init() {
    grep -q '^POSTGRES_PASSWORD=' "$HOME_DIR/host.env" || printf 'POSTGRES_PASSWORD=%s\n' "$(secret 24)" >>"$HOME_DIR/host.env"
    widen_docker_pools
    [[ -s "$HOME_DIR/caddy/staff" ]] || die "Add a staff sign-in to $HOME_DIR/caddy/staff first (cloud/site/README.md)."
    mkdir -p "$HOME_DIR/run" "$HOME_DIR/site"
    id lonora-site >/dev/null 2>&1 || run useradd --system --home-dir "$HOME_DIR/site" --shell /usr/sbin/nologin lonora-site
    run chown lonora-site "$HOME_DIR/run" "$HOME_DIR/site"
    chmod 755 "$HOME_DIR" "$HOME_DIR/run" "$HOME_DIR/caddy" "$HOME_DIR/caddy/customers"
    chmod 600 "$HOME_DIR/caddy/staff"
    run docker compose -f "$HOST/compose.yml" --env-file "$HOME_DIR/host.env" up -d --wait
    # The website may run exactly two commands as root: create and remove a customer.
    printf 'lonora-site ALL=(root) NOPASSWD: %s create *, %s remove *\n' "$HOST/customer.sh" "$HOST/customer.sh" |
        run_in install -m 440 /dev/stdin /etc/sudoers.d/lonora-site
    run visudo -cqf /etc/sudoers.d/lonora-site
    run install -m 644 "$HOST/lonora-site.service" /etc/systemd/system/lonora-site.service
    run install -m 644 "$HOST/lonora-backup.service" "$HOST/lonora-backup.timer" /etc/systemd/system/
    run systemctl daemon-reload
    run systemctl enable --now lonora-site lonora-backup.timer
    say "Host ready. Next: customer.sh release <git-ref>."
}

# Every night: the shared PostgreSQL (every customer's database and role), the website's database,
# and the keys without which they cannot be used (each customer's .env with its encryption key, the
# host and site settings, the staff sign-ins). Workspaces are not included (D10). Kept on this disk,
# mode 700, the last BACKUP_KEEP (7); the provider's server backup is the copy off this disk.
backup() {
    local out keep="${BACKUP_KEEP:-7}" old f keys=()
    out="$HOME_DIR/backups/$(date -u +%Y%m%d-%H%M%S)"
    mkdir -p "$out"
    if $DRY; then
        say "would run: docker exec lonora-postgres pg_dumpall -U postgres | gzip > $out/postgres.sql.gz"
    else
        docker exec lonora-postgres pg_dumpall -U postgres | gzip >"$out/postgres.sql.gz"
    fi
    if [[ -f "$HOME_DIR/site/site.db" ]]; then # a consistent copy while the site runs
        run node --no-warnings -e 'const [src, dst] = process.argv.slice(1), q = String.fromCharCode(39);
new (require("node:sqlite").DatabaseSync)(src).exec(`VACUUM INTO ${q}${dst.replaceAll(q, q + q)}${q}`)' "$HOME_DIR/site/site.db" "$out/site.db"
    fi
    for f in host.env site.env release.env caddy "$HOME_DIR"/customers/*/.env; do
        f="${f#"$HOME_DIR"/}"
        if [[ -e "$HOME_DIR/$f" ]]; then keys+=("$f"); fi
    done
    tar -czf "$out/keys.tar.gz" -C "$HOME_DIR" "${keys[@]}"
    for old in $(find "$HOME_DIR/backups" -mindepth 1 -maxdepth 1 -type d -name '2*' | sort | head -n "-$keep"); do
        rm -rf -- "$old"
    done
    say "Backup: $out"
}

case "${1:-}" in
    init) lock 60; init ;;
    release) release "${2:-}" ;;
    create | update | remove) customer "${2:-}"; lock 60; "$1" "${@:3}" ;;
    workspace) customer "${2:-}"; lock 60; workspace "${3:-}" ;;
    backup) backup ;;
    *) sed -n '4,10p' "$0" >&2; exit 2 ;;
esac
