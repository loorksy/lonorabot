#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == '--apply' ]] || { echo 'Run with --apply as root to enable unattended security updates and firewall rules for SSH and HTTPS.'; exit 0; }
[[ "$EUID" -eq 0 ]] || { echo 'Root is required.' >&2; exit 1; }
apt-get update
apt-get install -y unattended-upgrades ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now unattended-upgrades
echo 'Host firewall and unattended security updates enabled. Keep PostgreSQL private.'

cat >/etc/systemd/system/lonora-backup.service <<'UNIT'
[Unit]
Description=Lonora encrypted settings, database and artifact backup
[Service]
Type=oneshot
WorkingDirectory=/opt/lonora
ExecStart=/usr/bin/bash /opt/lonora/infra/compose/backup-prod.sh
UMask=0077
UNIT
cp /opt/lonora/infra/systemd/lonora-backup.timer /etc/systemd/system/lonora-backup.timer
systemctl daemon-reload
systemctl enable --now lonora-backup.timer
