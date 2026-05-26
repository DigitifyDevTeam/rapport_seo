#!/usr/bin/env bash
# One-time (or after git pull): fix "Permission denied" on ./cron_*.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
chmod +x cron_docker_run_all_clients.sh cron_docker_monthly_reports.sh cron_monthly_reports.sh 2>/dev/null || true
chmod +x docker-entrypoint.sh run_monthly_pipeline.sh 2>/dev/null || true
find "${ROOT}/scripts" -maxdepth 1 -name '*.sh' -type f -exec chmod +x {} +
echo "Executable: cron_docker_run_all_clients.sh"
ls -l "${ROOT}/cron_docker_run_all_clients.sh"
