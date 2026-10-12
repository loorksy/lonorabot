#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == '--apply' ]] || { echo 'Run with --apply as root to enable unattended security updates and firewall rules for SSH, HTTPS and LiveKit.'; exit 0; }
[[ "$EUID" -eq 0 ]] || { echo 'Root is required.' >&2; exit 1; }
apt-get update
apt-get install -y unattended-upgrades ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 7881/tcp
ufw allow 7882/udp
ufw --force enable
systemctl enable --now unattended-upgrades
echo 'Host firewall and unattended security updates enabled. Keep PostgreSQL private.'
