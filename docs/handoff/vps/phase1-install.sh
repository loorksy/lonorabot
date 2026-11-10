#!/usr/bin/env bash
# Phase 1: build the new Lonora on this server and install it SIDE BY SIDE (project lonora2, 127.0.0.1:18030).
# Changes nothing of the old stack, traefik or any other project. Usage: bash phase1-install.sh <full commit sha>
set -euo pipefail
REV="${1:?usage: phase1-install.sh <full commit sha of main>}"
SRC=/srv/lonorabot
if [ -d "$SRC/.git" ]; then git -C "$SRC" fetch -q origin main; else git clone -q https://github.com/loorksy/lonorabot "$SRC"; fi
git -C "$SRC" checkout -q --detach "$REV"
[ "$(git -C "$SRC" rev-parse HEAD)" = "$REV" ] || { echo "STOP: checkout is not $REV"; exit 1; }
VER="v$(date -u +%Y%m%d)-${REV:0:7}"
echo "== build $VER (capped: 1 cpu, 2g, nice/ionice)"
bash "$SRC/infra/compose/build-from-source.sh" --source "$SRC" --project lonora2 --version "$VER"
echo "== install side by side"
test -S /run/lonora-analysis/host.sock || { echo "STOP: analysis workspace socket missing"; exit 1; }
bash "$SRC/infra/compose/install.sh" --home /opt/lonora2 --project lonora2 \
  --behind-proxy 127.0.0.1:18030 --domain lonora.lork.cloud --env-from /opt/lonora/.env \
  --overlay infra/analysis/compose.workspace.yml --overlay infra/research/compose.research.yml \
  --version "127.0.0.1:5055/lonora:$VER"
echo "== carry the Android app and OTA updates over (read-only copies)"
install -d -m 755 /opt/lonora2/.runtime/releases/android /opt/lonora2/.runtime/releases/ota
cp -a /opt/lonora/downloads/lonora.apk /opt/lonora/downloads/lonora.json /opt/lonora2/.runtime/releases/android/
cp -a /opt/lonora/releases/ota/. /opt/lonora2/.runtime/releases/ota/
echo "== checks"
curl -fsS -m 10 http://127.0.0.1:18030/ready && echo
curl -fsS -m 10 -o /dev/null -I -w 'apk %{http_code} %{size_download}\n' http://127.0.0.1:18030/download/lonora.apk
"$(command -v lonora || echo /usr/local/bin/lonora-lonora2)" status || true
docker ps --format '{{.Names}} {{.Status}}' | sort
free -h | head -2; df -h / | tail -1
