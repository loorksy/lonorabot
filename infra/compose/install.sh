#!/usr/bin/env bash
# Production installer. Needs Docker (with the Compose plugin), gpg and coreutils only:
# no Python, Node, pnpm or source checkout. Everything else comes from the server image.
#
#   sudo bash install.sh --domain lonora.example.com [--version v0.3.0] [--home /opt/lonora]
#                        [--project lonora] [--behind-proxy 127.0.0.1:18030]
#                        [--min-free-ram-mb 3584] [--min-free-disk-gb 10] [--no-systemd]
#
#   --project       Compose project name: prefixes every container, volume and network, so
#                   this installation can run beside another one (default: lonora).
#   --behind-proxy  An existing reverse proxy (e.g. traefik) owns 80/443: run Caddy in
#                   plain HTTP on this loopback address:port only. Nothing binds 80/443.
#   --env-from FILE Reuse settings and secrets from an earlier installation's .env: only the
#                   keys this version knows (ENV_FROM_KEYS below) are copied; the database
#                   password is always new. Names are listed, values are never printed.
#   --overlay FILE  Add a Compose overlay from the bundle (repeatable), e.g.
#                   infra/analysis/compose.workspace.yml for the analysis workspace host.
#
# Get this file without a checkout:
#   docker run --rm --entrypoint cat ghcr.io/loorksy/lonorabot:main /app/deploy/infra/compose/install.sh >install.sh
#
# For a new installation only. A preflight checks the home directory, this project's
# containers and volumes, the ports, free memory and free disk, prints what it found, and
# refuses before changing anything. Secrets are generated here, mode 600, never printed.
set -euo pipefail
umask 077

home=/opt/lonora domain="" version=main systemd=true project=lonora proxy_listen="" env_from="" overlays=""
# Keys --env-from may copy. Everything else (database password, image, artifact root, LiveKit,
# overlays, project, ports) is set by this installer or not used by this version.
ENV_FROM_KEYS=" LONORA_DOMAIN LONORA_ENCRYPTION_KEY LONORA_BOOTSTRAP_TOKEN LONORA_WEBHOOK_SECRET LONORA_EXPO_ACCESS_TOKEN
 LONORA_PASSKEY_ANDROID_FINGERPRINTS LONORA_PASSKEY_ANDROID_PACKAGE LONORA_PASSKEY_IOS_APP_IDS
 LONORA_MAXIMUM_SUBAGENTS LONORA_MAXIMUM_TOOL_ROUNDS LONORA_RUN_LEASE_SECONDS LONORA_WORKER_POLL_SECONDS
 LONORA_SESSION_SECONDS LONORA_LOG_LEVEL LONORA_MCP_DECLARATIONS LONORA_MCP_OWNER_TRUST
 LONORA_OPENAI_API_KEY LONORA_ANTHROPIC_API_KEY LONORA_DEEPSEEK_API_KEY LONORA_ZAI_API_KEY LONORA_OPENROUTER_API_KEY
 LONORA_OPENAI_COMPATIBLE_BASE_URL LONORA_OPENAI_COMPATIBLE_API_KEY "
ENV_FROM_KEYS=" ${ENV_FROM_KEYS//$'\n'/ } "   # one space around every name, for the " $name " match
min_ram_mb="${LONORA_MIN_FREE_RAM_MB:-3584}" min_disk_gb="${LONORA_MIN_FREE_DISK_GB:-10}"
repo="${LONORA_IMAGE_REPO:-ghcr.io/loorksy/lonorabot}"
domain_given=false
while (($#)); do
    case "$1" in
        --domain) domain="${2:?}"; domain_given=true; shift 2 ;;
        --version) version="${2:?}"; shift 2 ;;
        --home) home="${2:?}"; shift 2 ;;
        --project) project="${2:?}"; shift 2 ;;
        --behind-proxy) proxy_listen="${2:?}"; shift 2 ;;
        --env-from) env_from="${2:?}"; shift 2 ;;
        --overlay) overlays+="${overlays:+ }${2:?}"; shift 2 ;;
        --min-free-ram-mb) min_ram_mb="${2:?}"; shift 2 ;;
        --min-free-disk-gb) min_disk_gb="${2:?}"; shift 2 ;;
        --no-systemd) systemd=false; shift ;;
        *) echo "Unknown option $1" >&2; exit 2 ;;
    esac
done
say() { printf 'install: %s\n' "$*"; }
die() { printf 'install: %s\n' "$*" >&2; exit 1; }

[[ "$EUID" -eq 0 || -n "${LONORA_INSTALL_ALLOW_NON_ROOT:-}" ]] || die 'Run as root (sudo).'
command -v docker >/dev/null || die 'Docker is required: https://docs.docker.com/engine/install/'
docker compose version >/dev/null 2>&1 || die 'The Docker Compose plugin is required (package docker-compose-plugin).'
if [[ -n "$env_from" ]]; then
    [[ -r "$env_from" && -f "$env_from" ]] || die "--env-from $env_from is not a readable file."
    env_from="$(readlink -f "$env_from")"
    if [[ -z "$domain" ]]; then domain="$(sed -n 's/^LONORA_DOMAIN=//p' "$env_from" | tail -n 1 | tr -d "\"'")"; fi
fi
[[ -n "$domain" ]] || die '--domain is required (or a LONORA_DOMAIN in --env-from).'

# --- preflight: read only; refuse before anything is created -------------------------
problems=0
check() { # $1 true|false, $2 message
    if "$1"; then say "  ok    $2"; else say "  FAIL  $2"; problems=$((problems + 1)); fi
}
port_in_use() { # $1 port: any listener on the host, or a container publishing it
    if command -v ss >/dev/null && [[ -n "$(ss -Hltn "( sport = :$1 )" 2>/dev/null)" ]]; then return 0; fi
    if docker ps --format '{{.Ports}}' | tr ',' '\n' | grep -qE ":$1->"; then return 0; fi
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}
existing_dir() { local dir="$1"; while [[ ! -d "$dir" ]]; do dir="$(dirname "$dir")"; done; printf '%s\n' "$dir"; }
# Parse one .env line into EL_NAME / EL_VALUE (an "export " prefix and leading spaces are
# allowed). 0: a setting; 1: blank or comment; 2: not NAME=VALUE; 3: CRLF; 4: control character.
env_line() {
    local line="$1"
    EL_NAME=""; EL_VALUE=""
    [[ "$line" != *$'\r' ]] || { EL_NAME="${line%%=*}"; return 3; }
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -n "$line" && "$line" != \#* ]] || return 1
    if [[ "$line" == "export "* ]]; then line="${line#export }"; line="${line#"${line%%[![:space:]]*}"}"; fi
    [[ "$line" == *=* ]] || return 2
    EL_NAME="${line%%=*}"; EL_VALUE="${line#*=}"
    [[ "$EL_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 2
    [[ "$EL_VALUE" != *[[:cntrl:]]* ]] || return 4
    return 0
}

say "Preflight for project '$project' in $home (nothing is changed unless every check passes):"
if [[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then check true "project name '$project'"; else check false "project name '$project' (use lowercase letters, digits, - or _)"; fi
if [[ -e "$home/state/image.env" || -e "$home/.env" || -e "$home/infra" ]]; then
    check false "$home already holds an installation (to start it: sudo lonora start; to update it: sudo lonora update <version>)"
else
    check true "$home holds no installation"
fi
if docker volume inspect "${project}_database" >/dev/null 2>&1; then
    check false "Docker volume ${project}_database already exists; a new install would reuse its data (archive and remove it, or choose another --project)"
else
    check true "no ${project}_database volume"
fi
taken=""
for volume in artifacts caddy-data caddy-config; do
    if docker volume inspect "${project}_$volume" >/dev/null 2>&1; then taken+=" ${project}_$volume"; fi
done
if docker network inspect "${project}_default" >/dev/null 2>&1; then taken+=" ${project}_default"; fi
if [[ -n "$taken" ]]; then check false "Docker names of project '$project' already exist:$taken"; else check true "no other volume or network named ${project}_*"; fi
others="$(docker ps -aq --filter "label=com.docker.compose.project=$project" | wc -l)"
if ((others > 0)); then check false "$others container(s) of Compose project '$project' already exist"; else check true "no containers of project '$project'"; fi
if [[ -n "$proxy_listen" ]]; then
    if [[ "$proxy_listen" =~ ^127\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3}):([0-9]{1,5})$ ]] &&
        ((10#${BASH_REMATCH[1]} <= 255 && 10#${BASH_REMATCH[2]} <= 255 && 10#${BASH_REMATCH[3]} <= 255 &&
          10#${BASH_REMATCH[4]} >= 1 && 10#${BASH_REMATCH[4]} <= 65535)); then
        port="$((10#${BASH_REMATCH[4]}))"
        if port_in_use "$port"; then check false "port $port is in use (behind-proxy $proxy_listen)"; else check true "port $port is free (behind-proxy $proxy_listen, loopback only)"; fi
    else
        check false "--behind-proxy $proxy_listen must be a loopback address:port, e.g. 127.0.0.1:18030"
    fi
else
    for port in 80 443; do
        if port_in_use "$port"; then check false "port $port is in use (use --behind-proxy if a reverse proxy owns it)"; else check true "port $port is free"; fi
    done
fi
for overlay in $overlays; do
    case "$overlay" in
        infra/analysis/compose.workspace.yml)
            if [[ -S /run/lonora-analysis/host.sock ]]; then check true "overlay $overlay: workspace host socket /run/lonora-analysis/host.sock is up"
            else say "  warn  overlay $overlay: /run/lonora-analysis/host.sock is missing; Lonora starts, analysis stays unavailable until lonora-analysis.service runs"; fi ;;
        *) check false "overlay $overlay is not one of the bundled overlays" ;;
    esac
done
if [[ -n "$env_from" ]]; then
    number=0 bad=0
    while IFS= read -r raw || [[ -n "$raw" ]]; do
        number=$((number + 1)); result=0
        env_line "$raw" || result=$?
        case "$result" in
            2) say "  FAIL  --env-from line $number is not NAME=VALUE"; bad=$((bad + 1)) ;;
            3) say "  FAIL  --env-from line $number (${EL_NAME:-?}) has a Windows line ending (CRLF)"; bad=$((bad + 1)) ;;
            4) say "  FAIL  --env-from $EL_NAME has a control character in its value"; bad=$((bad + 1)) ;;
        esac
    done <"$env_from"
    if ((bad > 0)); then problems=$((problems + bad)); else check true "--env-from $env_from: $number lines, all readable"; fi
fi
ram_mb=$(($(sed -n 's/^MemAvailable: *\([0-9]*\) kB/\1/p' /proc/meminfo) / 1024))
if ((ram_mb >= min_ram_mb)); then check true "available memory ${ram_mb} MB (need ${min_ram_mb} MB)"; else check false "available memory ${ram_mb} MB, below ${min_ram_mb} MB (the stack is limited to about 3.4 GB)"; fi
disk_dir="$(existing_dir "$home")"
disk_gb=$(($(df -Pm "$disk_dir" | awk 'NR==2 {print $4}') / 1024))
if ((disk_gb >= min_disk_gb)); then check true "free disk ${disk_gb} GB at $disk_dir (need ${min_disk_gb} GB)"; else check false "free disk ${disk_gb} GB at $disk_dir, below ${min_disk_gb} GB"; fi
((problems == 0)) || die "Preflight failed ($problems problem(s)); nothing was changed."

if ! command -v gpg >/dev/null; then
    if command -v apt-get >/dev/null && [[ "$EUID" -eq 0 ]]; then apt-get install -y -q gnupg >/dev/null; else die 'gpg is required (package gnupg).'; fi
fi

# --- install ----------------------------------------------------------------------------
if [[ "$version" == *@sha256:* || "$version" == */* ]]; then ref="$version"; else ref="$repo:$version"; fi
say "Pulling $ref"
docker pull -q "$ref" >/dev/null || die "Cannot pull $ref; nothing was changed."
if [[ "$ref" == *@sha256:* ]]; then pinned="$ref"; else
    pinned="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$ref" | grep -m1 "^${ref%:*}@sha256:")" || die "$ref has no registry digest."
fi

mkdir -p "$home"; chmod 750 "$home"; cd "$home"
mkdir -p state backups .runtime/releases/android .runtime/releases/ota
chmod 700 state backups
# Caddy reads the maintenance flag (`lonora` creates maintenance/on during updates).
mkdir -p maintenance && chmod 755 maintenance
# The API (uid 10001) reads OTA releases and the APK through a read-only mount.
chmod 755 .runtime .runtime/releases .runtime/releases/android .runtime/releases/ota

bundle="$(mktemp -d "$home/.bundle.XXXXXX")"
trap 'rm -rf "$bundle" "$home/.env.next"' EXIT
container="$(docker create "$pinned")"
docker cp -q "$container:/app/deploy/." "$bundle" && docker rm "$container" >/dev/null
[[ -x "$bundle/infra/compose/lonora" ]] || die "$pinned carries no deployment bundle."
# Explicit modes: containers read the mounted Caddyfile and overlays as other users.
(cd "$bundle" && find . -mindepth 1 -type d -exec chmod 755 {} + && find . -type f -perm -u+x -exec chmod 755 {} + && find . -type f ! -perm -u+x -exec chmod 644 {} +)
cp -a "$bundle/." .

random() { head -c "$1" /dev/urandom | base64 | tr -d '\n'; }
cat >.env <<EOF
# Lonora production configuration. Generated by install.sh; keep private (mode 600).
LONORA_DOMAIN=$domain
LONORA_PROJECT=$project
# Empty: Caddy on 80/443 (direct). Set: Caddy on this loopback address behind a reverse proxy.
LONORA_PROXY_LISTEN=$proxy_listen
LONORA_POSTGRES_PASSWORD=$(random 24 | tr '+/' 'xy' | tr -d '=')
LONORA_ENCRYPTION_KEY=$(random 32 | tr '+/' '-_')
LONORA_BOOTSTRAP_TOKEN=$(random 32 | tr '+/' '-_' | tr -d '=')
LONORA_WEBHOOK_SECRET=$(random 32 | tr '+/' '-_' | tr -d '=')
# Optional overlays, space separated, e.g. infra/analysis/compose.workspace.yml
LONORA_COMPOSE_OVERLAYS=$overlays
# Resource limits (defaults shown; about 3.4 GB in all):
# LONORA_DB_MEMORY=512m LONORA_DB_CPUS=0.5 LONORA_API_MEMORY=896m LONORA_API_CPUS=0.75
# LONORA_GATEWAY_MEMORY=768m LONORA_GATEWAY_CPUS=0.75 LONORA_CADDY_MEMORY=96m LONORA_CADDY_CPUS=0.25
# LONORA_SEARXNG_MEMORY=384m LONORA_SEARXNG_CPUS=0.25 LONORA_BROWSER_MEMORY=768m LONORA_BROWSER_CPUS=0.5
# Optional provider keys; the owner can also save encrypted keys in the Web settings.
LONORA_OPENAI_API_KEY=
LONORA_ANTHROPIC_API_KEY=
EOF
chmod 600 .env
say "Created $home/.env with freshly generated secrets."
if [[ -n "$env_from" ]]; then
    # Copy the known keys over the generated values; never print a value.
    copied="" ignored="" line="" name="" value=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        result=0; env_line "$line" || result=$?
        ((result == 1)) && continue
        ((result == 0)) || die "--env-from: line ${EL_NAME:-?} cannot be read; nothing more was changed."
        name="$EL_NAME"; value="$EL_VALUE"
        if [[ "$ENV_FROM_KEYS" != *" $name "* || ( "$name" == LONORA_DOMAIN && "$domain_given" == true ) ]]; then ignored+=" $name"; continue; fi
        [[ "$value" != *[[:cntrl:]]* ]] || die "--env-from: $name has a control character; nothing more was changed."
        # Mode 600 from the first byte (umask 077 is also set at the top); renamed into place.
        install -m 600 /dev/null .env.next
        { grep -v "^$name=" .env || true; printf '%s=%s\n' "$name" "$value"; } >>.env.next
        mv -f .env.next .env
        copied+=" $name"
    done <"$env_from"
    chmod 600 .env
    say "From $env_from copied:${copied:- nothing}"
    say "Not copied (set here, or not used by this version):${ignored:- nothing}"
fi
if [[ ! -f backup.key && -z "${LONORA_BACKUP_KEY:-}" ]]; then
    random 48 >backup.key
    chmod 600 backup.key
    say "Created the backup encryption key $home/backup.key."
fi
printf 'LONORA_IMAGE=%s\n' "$pinned" >state/image.env

# The command: /usr/local/bin/lonora unless another installation already owns that name.
link=/usr/local/bin/lonora
if [[ -e "$link" || -L "$link" ]] && [[ "$(readlink -f "$link")" != "$home/infra/compose/lonora" ]]; then link="/usr/local/bin/lonora-$project"; fi
ln -sfn "$home/infra/compose/lonora" "$link" 2>/dev/null && say "Command: $link" || link="$home/infra/compose/lonora"

if "$systemd" && command -v systemctl >/dev/null; then
    unit="$project-backup"
    sed -e "s#/opt/lonora#$home#g" -e "s#Lonora encrypted backup#Lonora ($project) encrypted backup#" infra/systemd/lonora-backup.service >"/etc/systemd/system/$unit.service"
    sed -e "s#lonora-backup.service#$unit.service#g" infra/systemd/lonora-backup.timer >"/etc/systemd/system/$unit.timer"
    chmod 644 "/etc/systemd/system/$unit.service" "/etc/systemd/system/$unit.timer"
    systemctl daemon-reload
    systemctl enable --now "$unit.timer"
    say "Daily encrypted backups enabled ($unit.timer)."
fi

"$home/infra/compose/lonora" start
if [[ -n "$proxy_listen" ]]; then
    entry="Point your reverse proxy for $domain at http://$proxy_listen (docs/operations.md, \"Side by side\")."
else
    entry="Open https://$domain."
fi
cat <<EOF

Lonora is installed in $home (project $project) and pinned to $pinned.
Next steps:
  1. Copy $home/backup.key to a safe place OFF this server. Without it, no backup can be restored.
  2. $entry Create the owner account with the one-time bootstrap token in
     $home/.env (sudo grep LONORA_BOOTSTRAP_TOKEN $home/.env); it is not shown here on purpose.
  3. Updates: sudo $link update <version>. Backups: sudo $link backup / restore-test.
EOF
