#!/usr/bin/env bash
# Offline export + signed publication. Does not require EAS, Expo login or a paid plan.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${1:-android}"
CHANNEL="${2:-production}"
case "$PLATFORM" in android|ios) ;; *) echo 'Platform must be android or ios' >&2; exit 2;; esac
case "$CHANNEL" in preview|production) ;; *) echo 'Channel must be preview or production' >&2; exit 2;; esac
export LONORA_OTA_CHANNEL="$CHANNEL"
OTA_EXPORT="$PROJECT_ROOT/.runtime/ota-export/$CHANNEL/$PLATFORM"
cd "$PROJECT_ROOT/apps/mobile"
pnpm exec expo export --platform "$PLATFORM" --output-dir "$OTA_EXPORT"
pnpm exec expo config --type public --json > "$OTA_EXPORT/expo-public.json"
RUNTIME_FILE="$(mktemp)"
trap 'rm -f "$RUNTIME_FILE"' EXIT
pnpm exec expo-updates runtimeversion:resolve --platform "$PLATFORM" > "$RUNTIME_FILE"
OTA_RUNTIME="$($PROJECT_ROOT/.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["runtimeVersion"])' "$RUNTIME_FILE")"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/ota-release.py" publish --export "$OTA_EXPORT" --platform "$PLATFORM" --channel "$CHANNEL" --runtime "$OTA_RUNTIME" --url "${LONORA_OTA_URL:-https://lonora.lork.cloud/api/mobile/updates}"
printf 'Published locally for %s / %s / runtime %s\n' "$CHANNEL" "$PLATFORM" "$OTA_RUNTIME"
