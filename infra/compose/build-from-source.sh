#!/usr/bin/env bash
# Build the server image on this host from a source checkout, when no published image
# exists (for example while CI is unavailable), and push it to a registry that listens
# on loopback only. Then install or update from it like any published image:
#
#   sudo bash infra/compose/build-from-source.sh --source /srv/lonorabot --project lonora2 --version v0.3.0
#   sudo bash install.sh ... --project lonora2 --version 127.0.0.1:5055/lonora:v0.3.0   (new install)
#   sudo lonora update 127.0.0.1:5055/lonora:v0.3.0                                     (update)
#
# The image is pinned by digest as always. The build runs in a dedicated BuildKit
# container capped at --cpus and --memory, with nice/ionice, so other projects on the host
# keep their share. The registry container ($PROJECT-registry, volume
# ${PROJECT}_registry) is started if it is not running; it binds 127.0.0.1 only.
#
# Options: --source DIR (required), --version TAG (default: the checkout's short commit),
# --project NAME (default lonora), --registry-port PORT (default 5055), --cpus N
# (default 1), --memory SIZE (default 2g).
# Environment, only where needed: LONORA_BUILD_CA_FILE (CA bundle of a TLS-intercepting
# proxy, given to the build as a secret), LONORA_TEST_SKIP_APT=1 (drop the Chromium/fonts
# apt-get line; only where the Debian mirror is unreachable — production needs them).
set -euo pipefail
umask 077

source_dir="" version="" project=lonora port=5055 cpus=1 memory=2g
while (($#)); do
    case "$1" in
        --source) source_dir="${2:?}"; shift 2 ;;
        --version) version="${2:?}"; shift 2 ;;
        --project) project="${2:?}"; shift 2 ;;
        --registry-port) port="${2:?}"; shift 2 ;;
        --cpus) cpus="${2:?}"; shift 2 ;;
        --memory) memory="${2:?}"; shift 2 ;;
        *) echo "Unknown option $1" >&2; exit 2 ;;
    esac
done
say() { printf 'build: %s\n' "$*"; }
die() { printf 'build: %s\n' "$*" >&2; exit 1; }
[[ -n "$source_dir" && -f "$source_dir/Dockerfile" ]] || die '--source must be a Lonora checkout (with a Dockerfile).'
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die '--project must be lowercase letters, digits, - or _.'
[[ "$port" =~ ^[0-9]{1,5}$ ]] || die '--registry-port must be a number.'
[[ "$cpus" =~ ^[0-9]+(\.[0-9]+)?$ ]] || die '--cpus must be a number.'
docker buildx version >/dev/null 2>&1 || die 'Docker buildx is required (package docker-buildx-plugin).'
source_dir="$(cd "$source_dir" && pwd)"
sha="$(git -C "$source_dir" rev-parse --short HEAD 2>/dev/null || echo unknown)"
version="${version:-$sha}"
image="127.0.0.1:$port/lonora:$version"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

registry="$project-registry"
if [[ -z "$(docker ps -q --filter "name=^${registry}\$")" ]]; then
    if [[ -n "$(docker ps -aq --filter "name=^${registry}\$")" ]]; then
        docker start "$registry" >/dev/null
    else
        say "Starting the loopback registry $registry on 127.0.0.1:$port"
        docker run -d --name "$registry" --restart unless-stopped -p "127.0.0.1:$port:5000" \
            -v "${project}_registry:/var/lib/registry" --memory 128m --cpus 0.25 registry:2 >/dev/null
    fi
fi

# A dedicated, capped BuildKit container; it reaches the loopback registry over plain HTTP.
builder="$project-builder"
{
    printf '[registry."127.0.0.1:%s"]\n  http = true\n' "$port"
    if [[ -n "${LONORA_BUILD_CA_FILE:-}" ]]; then
        printf '[registry."docker.io"]\n  mirrors = ["mirror.gcr.io"]\n[registry."mirror.gcr.io"]\n  ca = ["%s"]\n' "$LONORA_BUILD_CA_FILE"
    fi
} >"$work/buildkitd.toml"
quota="$(awk -v c="$cpus" 'BEGIN { printf "%d", c * 100000 }')"
docker buildx rm "$builder" >/dev/null 2>&1 || true
create=(docker buildx create --name "$builder" --driver docker-container --driver-opt network=host
    --driver-opt "cpu-quota=$quota" --driver-opt "memory=$memory" --config "$work/buildkitd.toml")
for var in HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; do
    if [[ -n "${!var:-}" ]]; then create+=(--driver-opt "env.$var=${!var}"); fi
done
"${create[@]}" >/dev/null
trap 'docker buildx rm "$builder" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

dockerfile="$work/Dockerfile"
if [[ -n "${LONORA_TEST_SKIP_APT:-}" ]]; then
    sed '/apt-get install -y --no-install-recommends fonts-dejavu-core chromium/d' "$source_dir/Dockerfile" >"$dockerfile"
else
    cp "$source_dir/Dockerfile" "$dockerfile"
fi
args=(--build-arg "LONORA_VERSION=$version" --build-arg "LONORA_GIT_SHA=$sha" --build-arg "LONORA_BUILT_AT=$(date -u +%FT%TZ)")
for var in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy; do args+=(--build-arg "$var"); done
if [[ -n "${LONORA_BUILD_CA_FILE:-}" ]]; then
    args+=(--secret "id=proxy_ca,src=$LONORA_BUILD_CA_FILE" --secret "id=system_ca,src=$LONORA_BUILD_CA_FILE")
fi
say "Building $image from $source_dir ($sha), capped at $cpus CPU and $memory"
nice -n 10 ionice -c 3 docker buildx build --builder "$builder" --progress plain -f "$dockerfile" "${args[@]}" --push -t "$image" "$source_dir" >"$work/build.log" 2>&1 ||
    { tail -40 "$work/build.log" >&2; die 'The build failed.'; }
docker pull -q "$image" >/dev/null
digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" | grep -m1 "^127.0.0.1:$port/lonora@sha256:")"
say "Built and pushed: $image"
say "Digest: $digest"
say "New install: sudo bash install.sh --project $project --version $image ...   Update: sudo lonora update $image"
