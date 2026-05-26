#!/usr/bin/env bash
# =============================================================================
# VPS cron entry point — all production clients + Google Drive upload.
#
# Configure when and how often this runs in your VPS cron / scheduled-task UI.
# Point the job at the full path to this file, for example:
#   /home/USER/public_html/rapport_seo/cron_monthly_reports.sh
#
# Optional manual arguments (do not set these in cron unless you need a fixed
# reporting month):
#   ./cron_monthly_reports.sh --month 2026-04
#
# Logs: logs/cron_reports_YYYY-MM-DD_HHMMSS.log
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/cron_reports_$(date +%Y-%m-%d_%H%M%S).log"
exec >>"${LOG_FILE}" 2>&1

echo "=== SEO reports pipeline started at $(date -Iseconds) ==="
echo "Working directory: ${ROOT}"
echo "Log file: ${LOG_FILE}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

VENV_PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "${VENV_PYTHON}" ]]; then
  VENV_PYTHON="$(command -v python3 || true)"
fi
if [[ -z "${VENV_PYTHON}" || ! -x "${VENV_PYTHON}" ]]; then
  echo "ERROR: Python not found. Create .venv or install python3."
  exit 127
fi

export DISPLAY="${DISPLAY:-:99}"
export PATH="${ROOT}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

LOCK_FILE="${ROOT}/logs/.cron_reports.lock"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "ERROR: Another report run is already in progress (lock: ${LOCK_FILE})"
  exit 75
fi

set +e
"${VENV_PYTHON}" -m src.pipeline.monthly_job "$@"
EXIT_CODE=$?
set -e

if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo "=== Pipeline finished OK at $(date -Iseconds) ==="
else
  echo "=== Pipeline FAILED (exit ${EXIT_CODE}) at $(date -Iseconds) ==="
fi
exit "${EXIT_CODE}"
