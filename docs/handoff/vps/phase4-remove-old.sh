#!/usr/bin/env bash
# Phase 4: permanently remove the OLD Lonora (compose project "lonora" in /opt/lonora), only after:
#   - lonora.yml routes to the new install (127.0.0.1:18030) and it answers /ready,
#   - the owner signed in on the new install and phase 3 imported the keys.
# Keeps: /opt/lonora-mobile-build (Android signing keystore), lonora-analysis.service (the new install uses it),
# traefik, and every other project. Usage: DRY_RUN=1 bash phase4-remove-old.sh, then without DRY_RUN.
set -euo pipefail
F=/docker/traefik/dynamic/lonora.yml
grep -q 'http://127.0.0.1:18030' "$F" && ! grep -q 'http://127.0.0.1:180[12]0' "$F" || { echo "STOP: lonora.yml still routes to the old stack"; exit 1; }
curl -fsS -m 10 http://127.0.0.1:18030/ready >/dev/null || { echo "STOP: the new install is not ready"; exit 1; }
cd /opt/lonora
OLD=(docker compose -p lonora -f docker-compose.yml)
"${OLD[@]}" ps -a --format '{{.Name}} {{.Image}} {{.State}}'
foreign=$(docker ps -a --filter label=com.docker.compose.project=lonora --format '{{.Names}}' | grep -vE '^lonora-(gateway|api|browser-1|searxng-1|downloads|db)$' || true)
[ -z "$foreign" ] || { echo "STOP: project lonora holds unexpected containers: $foreign"; exit 1; }
IMGS=$("${OLD[@]}" images -q 2>/dev/null | sort -u)
others() { docker ps -a --format '{{.Names}} {{.ID}} {{.State}}' | awk '$1 !~ /^lonora-(gateway|api|browser-1|searxng-1|downloads|db)$/ && $1 !~ /^lonora-analysis-[0-9a-f]+$/' | sort; }
others > /root/remove-old-lonora.before
if [ "${DRY_RUN:-0}" = 1 ]; then echo "DRY RUN: would run compose down --volumes for project lonora, remove images: $IMGS, and /opt/lonora"; exit 0; fi
"${OLD[@]}" down --volumes --remove-orphans
for i in $IMGS; do docker rmi "$i" >/dev/null 2>&1 && echo "removed image $i" || echo "kept image $i (in use by another container)"; done
cd /; rm -rf --one-file-system /opt/lonora
echo "== check"; others | diff /root/remove-old-lonora.before - && echo "other containers: unchanged"
docker volume ls --format '{{.Name}}' | grep -E '^lonora-(database|artifacts)$' && echo "!! old volumes left" || echo "old volumes: removed"
systemctl is-active lonora-analysis.service; curl -fsS -m 10 http://127.0.0.1:18030/ready && echo " new install ready"
