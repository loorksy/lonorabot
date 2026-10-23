#!/usr/bin/env bash
# Trusted administrator build, never callable from an analytical job.
set -euo pipefail
analysis_root="$(cd "$(dirname "$0")" && pwd)"
analysis_build="$(mktemp -d)"
trap 'rm -rf "$analysis_build"' EXIT
cp "$analysis_root/analytics.Dockerfile" "$analysis_build/Dockerfile"
cp "$analysis_root/analytics.requirements.lock" "$analysis_build/analytics.requirements.lock"
"${LONORA_BUILD_PYTHON:-python3}" -m pip download \
  --require-hashes --only-binary=:all: --no-deps \
  --python-version 3.12 --platform manylinux2014_x86_64 \
  --dest "$analysis_build/wheels" -r "$analysis_build/analytics.requirements.lock"
# No network is available even during package installation. The administrator
# must separately pull the exact reviewed base digest if it is not cached.
docker --host=unix:///var/run/docker.sock build --network=none \
  -t "${LONORA_ANALYTICS_IMAGE_TAG:-lonora-analysis:analytics}" "$analysis_build"
docker --host=unix:///var/run/docker.sock image inspect \
  "${LONORA_ANALYTICS_IMAGE_TAG:-lonora-analysis:analytics}" --format '{{.Id}}'
