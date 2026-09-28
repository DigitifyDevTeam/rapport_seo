#!/usr/bin/env bash
# =============================================================================
# Refresh Microsoft Clarity session cookies (keep-alive).
#
# Microsoft KMSI sessions still die if unused for weeks. Hit Clarity every few
# days so ESTSAUTHPERSISTENT slides forward. This does NOT generate reports.
#
# Crontab (every 3 days at 04:15 Europe/Paris):
#   15 4 */3 * * /home/new/public_html/rapport_seo/cron_clarity_keepalive.sh
#
# Logs: logs/clarity_keepalive_YYYY-MM-DD_HHMMSS.log
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}" "${ROOT}/outputs"
LOG_FILE="${LOG_DIR}/clarity_keepalive_$(date +%Y-%m-%d_%H%M%S).log"
exec >>"${LOG_FILE}" 2>&1

echo "=== Clarity keep-alive started at $(date -Iseconds) ==="
echo "Log: ${LOG_FILE}"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: Missing ${ROOT}/.env"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not installed"
  exit 127
fi

LOCK_FILE="${LOG_DIR}/.clarity_keepalive.lock"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "ERROR: Another Clarity keep-alive is in progress"
  exit 75
fi

set +e
bash "${ROOT}/scripts/clarity_ui_keepalive.sh"
EXIT_CODE=$?
set -e

if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo "=== Clarity keep-alive OK at $(date -Iseconds) ==="
else
  echo "=== Clarity keep-alive FAILED (exit ${EXIT_CODE}) at $(date -Iseconds) ==="
  echo "If sign-in was required, re-login:"
  echo "  bash scripts/clarity_ui_prepare_vnc_client.sh digitify"
fi
exit "${EXIT_CODE}"
