#!/usr/bin/env bash
# Build and push the five images tests/ops/lifecycle_test.sh needs, into REPO.
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
#   v3-broken  v2 + tests/ops/fixtures/9999_broken_probe.py (creates a table) and a Gateway
#              that never starts, so /ready never passes
#   v4-good    v2 + tests/ops/fixtures/9998_good_probe.py (a working migration)
# The probe migrations exist only inside these test images, never in packages/db/migrations.
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

echo "old: $old_sha"
git -C "$root" worktree add -q --detach "$work/old" "$old_sha"
build "$work/old" "$repo:old"

echo 'v1, v2: this checkout'
build "$root" "$repo:v1" --build-arg LONORA_VERSION=v1 --build-arg LONORA_GIT_SHA="$(git -C "$root" rev-parse --short HEAD)"
build "$root" "$repo:v2" --build-arg LONORA_VERSION=v2 --build-arg LONORA_GIT_SHA="$(git -C "$root" rev-parse --short HEAD)"
docker push -q "$repo:v2" >/dev/null   # v3/v4 build FROM it

# The probes chain onto whatever migration head v2 has.
base_head="$(docker run --rm --network none --entrypoint cat "$repo:v2" /app/release.json | sed -n 's/.*"migration_head": "\([^"]*\)".*/\1/p')"
[[ -n "$base_head" ]] || { echo 'v2 has no migration head' >&2; exit 1; }
echo "base migration head: $base_head"

echo 'v3-broken: schema-changing migration, Gateway never ready'
mkdir "$work/broken"
sed "s/__BASE_HEAD__/$base_head/" "$root/tests/ops/fixtures/9999_broken_probe.py" >"$work/broken/9999_broken_probe.py"
cat >"$work/broken/Dockerfile" <<EOF
FROM $repo:v2
COPY 9999_broken_probe.py /app/packages/db/migrations/versions/9999_broken_probe.py
USER root
RUN sed -i 's|exec lonora-gateway "\$@"|exec sleep infinity|' /app/entrypoint.sh && \\
    sed -i 's/"version": "v2"/"version": "v3-broken"/; s/"migration_head": "[^"]*"/"migration_head": "9999_broken_probe"/' /app/release.json /app/deploy/release.json
USER lonora
EOF
docker build -q -t "$repo:v3-broken" "$work/broken" >/dev/null

echo 'v4-good: working migration'
mkdir "$work/good"
sed "s/__BASE_HEAD__/$base_head/" "$root/tests/ops/fixtures/9998_good_probe.py" >"$work/good/9998_good_probe.py"
cat >"$work/good/Dockerfile" <<EOF
FROM $repo:v2
COPY 9998_good_probe.py /app/packages/db/migrations/versions/9998_good_probe.py
USER root
RUN sed -i 's/"version": "v2"/"version": "v4-good"/; s/"migration_head": "[^"]*"/"migration_head": "9998_good_probe"/' /app/release.json /app/deploy/release.json
USER lonora
EOF
docker build -q -t "$repo:v4-good" "$work/good" >/dev/null

mkdir -p "$root/.runtime"
out="$root/.runtime/ops-test-images.txt"
: >"$out"
for tag in old v1 v2 v3-broken v4-good; do
    docker push -q "$repo:$tag" >/dev/null
    digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$repo:$tag" | grep -m1 "^$repo@")"
    printf '%-10s %s\n' "$tag" "$digest" | tee -a "$out"
done
