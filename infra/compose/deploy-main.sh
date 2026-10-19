#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mode=--pull
backup=true
mode_selected=false
for argument in "$@"; do
    case "$argument" in
        --pull|--build)
            if "$mode_selected"; then echo 'Choose one deployment mode.' >&2; exit 2; fi
            mode="$argument"; mode_selected=true ;;
        --no-backup) backup=false ;;
        *) echo 'Usage: deploy-main.sh [--pull|--build] [--no-backup]' >&2; exit 2 ;;
    esac
done
[[ -z "$(git status --porcelain)" ]] || { echo 'Deployment checkout has local changes.' >&2; exit 1; }
git fetch origin main
git merge --ff-only origin/main
compose='infra/compose/docker-compose.prod.yml'
docker compose --env-file .env -f "$compose" config --quiet
if [[ "$mode" == '--build' ]]; then
    image="$(docker compose --env-file .env -f "$compose" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["api"]["image"])')"
    build_args=(--build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY)
    proxy_ca="${LONORA_BUILD_PROXY_CA_FILE:-${CODEX_PROXY_CERT:-}}"
    system_ca="${LONORA_BUILD_SYSTEM_CA_FILE:-/etc/ssl/certs/ca-certificates.crt}"
    if [[ -n "$proxy_ca" ]]; then
        [[ -f "$proxy_ca" ]] || { echo 'Build proxy CA file is missing.' >&2; exit 1; }
        build_args+=(--secret "id=proxy_ca,src=$proxy_ca")
    fi
    if [[ -f "$system_ca" ]]; then build_args+=(--secret "id=system_ca,src=$system_ca"); fi
    docker build "${build_args[@]}" --tag "$image" .
    docker compose --env-file .env -f "$compose" pull db caddy
else
    docker compose --env-file .env -f "$compose" pull
fi
# Back up an existing installation before migrations change the schema.
if "$backup" && [[ -n "$(docker compose --env-file .env -f "$compose" ps -q db)" ]]; then
    LONORA_COMPOSE_FILE="$compose" bash scripts/backup.sh
fi
docker compose --env-file .env -f "$compose" up -d --wait --remove-orphans
echo 'Main deployed. Check the authenticated workspace and /ready through your domain.'
