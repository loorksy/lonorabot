#!/usr/bin/env bash
# Phase 2: point lonora.lork.cloud (and /download) at the new install. Only lonora.yml's urls change.
# Every other site must answer exactly as before, otherwise lonora.yml is put back automatically.
set -euo pipefail
D=/docker/traefik/dynamic; F=$D/lonora.yml; BACK=/root/lonora.yml.before-switch
grep -q 'http://127.0.0.1:18010' "$F" || { echo "STOP: lonora.yml does not route to 127.0.0.1:18010"; exit 1; }
curl -fsS -m 10 http://127.0.0.1:18030/ready >/dev/null || { echo "STOP: the new install is not ready"; exit 1; }
curl -fsS -m 10 -o /dev/null -I http://127.0.0.1:18030/download/lonora.apk || { echo "STOP: the new install does not serve the APK"; exit 1; }
hosts=$(grep -rhoE 'Host\([^)]*\)' "$D" | grep -oE '`[^`]+`' | tr -d '`' | sort -u)
probe() { for h in $hosts; do
  echo "$h https=$(curl -s -o /dev/null -m 10 -w '%{http_code}/%{ssl_verify_result}' --resolve "$h:443:127.0.0.1" "https://$h/") http=$(curl -s -o /dev/null -m 10 -w '%{http_code}' --resolve "$h:80:127.0.0.1" "http://$h/")"; done; }
probe > /root/switch-sites-before.txt; cat /root/switch-sites-before.txt
cp -p "$F" "$BACK"
sed -e 's#http://127.0.0.1:18010#http://127.0.0.1:18030#' -e 's#http://127.0.0.1:18020#http://127.0.0.1:18030#' "$F" > "$D/.lonora.yml.tmp"
diff "$F" "$D/.lonora.yml.tmp" || true
python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1]))' "$D/.lonora.yml.tmp"
mv "$D/.lonora.yml.tmp" "$F"
sleep 8
probe > /root/switch-sites-after.txt; cat /root/switch-sites-after.txt
ok=1
diff <(grep -v '^lonora.lork.cloud ' /root/switch-sites-before.txt) <(grep -v '^lonora.lork.cloud ' /root/switch-sites-after.txt) || ok=0
grep -qE '^lonora.lork.cloud https=(200|30[0-9])/0 ' /root/switch-sites-after.txt || ok=0
curl -fsS -m 10 --resolve lonora.lork.cloud:443:127.0.0.1 https://lonora.lork.cloud/ready >/dev/null || ok=0
code=$(curl -s -o /dev/null -I -m 15 -w '%{http_code}' --resolve lonora.lork.cloud:443:127.0.0.1 https://lonora.lork.cloud/download/lonora.apk); [ "$code" = 200 ] || ok=0
if [ "$ok" = 1 ]; then echo "SWITCHED: lonora.lork.cloud now serves the new install; /download/lonora.apk $code"; else
  cp -p "$BACK" "$F"; echo "REVERTED: something did not answer as expected; lonora.yml put back (old stack serves again)"; exit 1; fi
