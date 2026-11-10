#!/usr/bin/env bash
# Kept for existing timers: production backups are made by `lonora backup` (encrypted).
set -euo pipefail
exec "$(dirname "$0")/lonora" backup
