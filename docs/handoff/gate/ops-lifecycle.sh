#!/usr/bin/env bash
# Runs the ops lifecycle test (PR #43) against a checkout, with a throwaway local registry.
# Usage: ops-lifecycle.sh <checkout of ops/install-update-backup or main after #43>
# If Docker Hub answers 429, pre-pull the base images from mirror.gcr.io and tag them locally:
#   docker pull mirror.gcr.io/library/node:22-bookworm-slim && docker tag mirror.gcr.io/library/node:22-bookworm-slim node:22-bookworm-slim
#   docker pull mirror.gcr.io/library/python:3.12-slim-bookworm && docker tag mirror.gcr.io/library/python:3.12-slim-bookworm python:3.12-slim-bookworm
set -u
cd "${1:?checkout}"
docker rm -f registry >/dev/null 2>&1; docker run -d --name registry -p 127.0.0.1:5000:5000 registry:2 >/dev/null
# LONORA_TEST_SKIP_APT=1 skips apt in the test image when the Debian mirror is unreachable;
# LONORA_BUILD_CA_FILE / LONORA_BUILD_NETWORK=host are only needed behind a TLS-intercepting proxy.
bash tests/ops/build_test_images.sh localhost:5000/lonora && sudo -E bash tests/ops/lifecycle_test.sh localhost:5000/lonora
