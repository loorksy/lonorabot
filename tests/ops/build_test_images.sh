#!/usr/bin/env bash
# Build and push the seven images tests/ops/lifecycle_test.sh needs, into REPO.
#
#   bash tests/ops/build_test_images.sh REPO
#   bash tests/ops/lifecycle_test.sh REPO
#
# REPO is a repository in a registry you control, for example a local one:
#   docker run -d --name registry -p 127.0.0.1:5000:5000 registry:2
#   bash tests/ops/build_test_images.sh localhost:5000/lonora
#
# Tags (digests are printed and written to .runtime/ops-test-images.txt):
#   old        main at OLD_SHA, the last commit before this tooling: no /app/deploy, no manifest
#   v1, v2     this checkout, built twice with LONORA_VERSION=v1 / v2 (different digests)
#   v4-good    v2 + tests/ops/fixtures/9998_good_probe.py (a working migration)
#   v3-broken  v4-good's migration + 9999_broken_probe.py (creates a table), with a Gateway
#              that never starts, so /ready never passes
#   v3-broken2 v3-broken under another version (a second failing release, other digest)
#   v3-fixed   the same migrations as v3-broken with a working Gateway (the "fixed version")
# The probes form a linear chain (v2's head -> 9998 -> 9999), so every update the
# lifecycle test makes between these images is an upgrade. They exist only inside these
# test images, never in packages/db/migrations.
#
# Environment:
#   OLD_SHA                  commit for "old" (default 80e195f, main before this tooling)
#   LONORA_TEST_SKIP_APT=1   drop the Chromium/fonts apt-get line (only where the Debian mirror
#                            is unreachable; /ready does not need them, charts do)
#   LONORA_BUILD_CA_FILE     a CA bundle for a TLS-intercepting proxy, passed as build secrets
#   LONORA_BUILD_NETWORK     docker build --network value (e.g. host, for a proxy on 127.0.0.1)
set -euo pipefail
repo="${1:?Usage: build_test_images.sh REPO}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
old_sha="${OLD_SHA:-80e195f}"
work="$(mktemp -d)"
trap 'git -C "$root" worktree remove --force "$work/old" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT

build() { # $1 source dir, $2 tag, rest: extra docker build args
    local src="$1" tag="$2"; shift 2
    local dockerfile="$work/Dockerfile.$RANDOM"
    if [[ -n "${LONORA_TEST_SKIP_APT:-}" ]]; then
        sed '/apt-get install -y --no-install-recommends fonts-dejavu-core chromium/d' "$src/Dockerfile" >"$dockerfile"
    else
        cp "$src/Dockerfile" "$dockerfile"
    fi
    local args=(--build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY --build-arg http_proxy --build-arg https_proxy)
    if [[ -n "${LONORA_BUILD_CA_FILE:-}" ]]; then
        args+=(--secret "id=proxy_ca,src=$LONORA_BUILD_CA_FILE" --secret "id=system_ca,src=$LONORA_BUILD_CA_FILE")
    fi
    if [[ -n "${LONORA_BUILD_NETWORK:-}" ]]; then args+=(--network "$LONORA_BUILD_NETWORK"); fi
    DOCKER_BUILDKIT=1 docker build -q -f "$dockerfile" "${args[@]}" "$@" -t "$tag" "$src" >/dev/null
}

# A probe image: v2 plus fixture migrations, a new release head, and optionally a Gateway
# that never starts.
probe_image() { # $1 tag, $2 migration head, $3 broken|ok, rest: fixture files in order
    local tag="$1" head="$2" broken="$3" dir="$work/$1" fixture
    shift 3
    mkdir "$dir"
    {
        printf 'FROM %s:v2\n' "$repo"
        for fixture in "$@"; do
            sed "s/__BASE_HEAD__/$base_head/" "$root/tests/ops/fixtures/$fixture" >"$dir/$fixture"
            printf 'COPY %s /app/packages/db/migrations/versions/%s\n' "$fixture" "$fixture"
        done
        printf 'USER root\n'
        if [[ "$broken" == broken ]]; then
            printf '%s\n' "RUN sed -i 's|exec lonora-gateway \"\$@\"|exec sleep infinity|' /app/entrypoint.sh"
        fi
        printf '%s\n' "RUN sed -i 's/\"version\": \"v2\"/\"version\": \"$tag\"/; s/\"migration_head\": \"[^\"]*\"/\"migration_head\": \"$head\"/' /app/release.json /app/deploy/release.json"
        printf 'USER lonora\n'
    } >"$dir/Dockerfile"
    docker build -q -t "$repo:$tag" "$dir" >/dev/null
}

echo "old: $old_sha"
git -C "$root" worktree add -q --detach "$work/old" "$old_sha"
build "$work/old" "$repo:old"

echo 'v1, v2: this checkout'
build "$root" "$repo:v1" --build-arg LONORA_VERSION=v1 --build-arg LONORA_GIT_SHA="$(git -C "$root" rev-parse --short HEAD)"
build "$root" "$repo:v2" --build-arg LONORA_VERSION=v2 --build-arg LONORA_GIT_SHA="$(git -C "$root" rev-parse --short HEAD)"
docker push -q "$repo:v2" >/dev/null   # the probe images build FROM it

# The probes chain onto whatever migration head v2 has.
base_head="$(docker run --rm --network none --entrypoint cat "$repo:v2" /app/release.json | sed -n 's/.*"migration_head": "\([^"]*\)".*/\1/p')"
[[ -n "$base_head" ]] || { echo 'v2 has no migration head' >&2; exit 1; }
echo "base migration head: $base_head"
echo 'v4-good: + 9998'
probe_image v4-good 9998_good_probe ok 9998_good_probe.py
echo 'v3-broken: + 9998 + 9999, Gateway never ready'
probe_image v3-broken 9999_broken_probe broken 9998_good_probe.py 9999_broken_probe.py
echo 'v3-broken2: the same as v3-broken under another version'
probe_image v3-broken2 9999_broken_probe broken 9998_good_probe.py 9999_broken_probe.py
echo 'v3-fixed: + 9998 + 9999'
probe_image v3-fixed 9999_broken_probe ok 9998_good_probe.py 9999_broken_probe.py

mkdir -p "$root/.runtime"
out="$root/.runtime/ops-test-images.txt"
: >"$out"
for tag in old v1 v2 v4-good v3-broken v3-broken2 v3-fixed; do
    docker push -q "$repo:$tag" >/dev/null
    digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$repo:$tag" | grep -m1 "^$repo@")"
    printf '%-10s %s\n' "$tag" "$digest" | tee -a "$out"
done
