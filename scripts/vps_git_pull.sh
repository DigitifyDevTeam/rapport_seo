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
echo "Done. Restash list: git stash list"
