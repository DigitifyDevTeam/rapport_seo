#!/usr/bin/env bash
# =============================================================================
# VPS cron / "tâche planifiée" — all clients + Google Drive (Docker).
#
# Configure your hosting panel to run this file monthly (no arguments).
# Example command in the panel:
#   /home/USER/public_html/rapport_seo/cron_docker_run_all_clients.sh
#
# Do NOT pass a fixed month (e.g. 2026-04). The month is chosen automatically
# from the run date and REPORT_CYCLE_DAY / SEO_REPORT_SCHEDULE_DAY in .env.
#
# Optional manual rerun for one month only:
#   ./cron_docker_run_all_clients.sh --month 2026-04
#
# Logs: logs/cron_docker_all_YYYY-MM-DD_HHMMSS.log
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}" "${ROOT}/outputs" "${ROOT}/secrets"
LOG_FILE="${LOG_DIR}/cron_docker_all_$(date +%Y-%m-%d_%H%M%S).log"
exec >>"${LOG_FILE}" 2>&1

echo "=== SEO Docker (all clients + Drive) started at $(date -Iseconds) ==="
echo "Project: ${ROOT}"
echo "Log: ${LOG_FILE}"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: Missing ${ROOT}/.env"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not installed"
  exit 127
fi

LOCK_FILE="${LOG_DIR}/.cron_docker_all.lock"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "ERROR: Another all-clients Docker run is in progress"
  exit 75
fi

set +e
"${ROOT}/scripts/docker_run_all_clients.sh" "$@"
EXIT_CODE=$?
set -e

if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo "=== Finished OK at $(date -Iseconds) ==="
else
  echo "=== FAILED (exit ${EXIT_CODE}) at $(date -Iseconds) ==="
fi
exit "${EXIT_CODE}"
