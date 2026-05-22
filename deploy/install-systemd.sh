#!/usr/bin/env bash
# Install systemd service + timer on a Linux VPS.
# Usage (as root): sudo bash deploy/install-systemd.sh /opt/rapport_seo
set -euo pipefail

APP_DIR="${1:-/opt/rapport_seo}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "Missing ${APP_DIR}/.env — copy .env.example and configure secrets first."
  exit 1
fi

sed "s|/opt/rapport_seo|${APP_DIR}|g" "${SCRIPT_DIR}/seo-reports.service" \
  > /etc/systemd/system/seo-reports.service
cp "${SCRIPT_DIR}/seo-reports.timer" /etc/systemd/system/seo-reports.timer

systemctl daemon-reload
systemctl enable seo-reports.timer
systemctl start seo-reports.timer
systemctl status seo-reports.timer --no-pager

echo ""
echo "Timer installed. Test once:"
echo "  sudo systemctl start seo-reports.service"
echo "  journalctl -u seo-reports.service -f"
