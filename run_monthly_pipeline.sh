#!/usr/bin/env bash
# =============================================================================
# SINGLE ENTRY POINT for your VPS panel timer (one file, day 26 each month).
#
# In the VPS control panel, create a scheduled task:
#   - Schedule: every month, day 26, time 06:00 (Europe/Paris)
#   - Command / script to run (use the FULL path on your server):
#       /opt/rapport_seo/run_monthly_pipeline.sh
#
# This runs all 4 production clients + uploads reports to Google Drive.
# Logs: logs/monthly_pipeline_YYYY-MM-DD_HHMMSS.log
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/monthly_pipeline_$(date +%Y-%m-%d_%H%M%S).log"
exec >>"${LOG_FILE}" 2>&1

echo "=== SEO monthly pipeline started at $(date -Iseconds) ==="
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
  VENV_PYTHON="python3"
fi

export DISPLAY="${DISPLAY:-:99}"

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
