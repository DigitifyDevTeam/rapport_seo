#!/usr/bin/env bash
# Safe git pull on the VPS when hosting panels edited cron scripts locally.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
echo "Stashing local VPS edits (if any)..."
git stash push -u -m "vps-local-$(date +%Y%m%d)" \
  -- cron_docker_run_all_clients.sh scripts/docker_run_all_clients.sh 2>/dev/null \
  || git stash push -u -m "vps-local-$(date +%Y%m%d)" || true
git pull
echo "Ensuring shell scripts are executable..."
find "${ROOT}" -maxdepth 2 -name '*.sh' -type f -exec chmod +x {} +
find "${ROOT}/scripts" -maxdepth 1 -name '*.sh' -type f -exec chmod +x {} +
chmod +x "${ROOT}/cron_docker_run_all_clients.sh" "${ROOT}/cron_docker_monthly_reports.sh" 2>/dev/null || true
echo "Done. Run: ./cron_docker_run_all_clients.sh"
