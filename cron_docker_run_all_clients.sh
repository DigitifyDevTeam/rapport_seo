#!/usr/bin/env bash
# =============================================================================
# VPS cron / "tâche planifiée" — all clients + Google Drive (Docker).
#
# Panel command (no arguments):
#   /bin/bash /home/USER/public_html/rapport_seo/cron_docker_run_all_clients.sh
#
# After git pull on the server, this script runs "docker compose build" automatically.
# Logs: logs/cron_docker_all_YYYY-MM-DD_HHMMSS.log
#
# GMB: prepare on Windows, copy gmb-<client>.json to VPS (see Origincbd).
# Advisory: check_gmb_vps_sessions.py (does not block cron).
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

# Cron often has a minimal PATH — docker is usually under /usr/bin or /usr/local/bin.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}" "${ROOT}/outputs" "${ROOT}/secrets"
LOG_FILE="${LOG_DIR}/cron_docker_all_$(date +%Y-%m-%d_%H%M%S).log"

# Run the pipeline inside the log file; print one line for the hosting panel.
{
  echo "=== SEO Docker (all clients + Drive) started at $(date -Iseconds) ==="
  echo "Project: ${ROOT}"
  echo "Log: ${LOG_FILE}"

  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "ERROR: Missing ${ROOT}/.env"
    exit 1
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not in PATH (cron PATH is limited). Install docker or fix PATH."
    exit 127
  fi

  COMPOSE=(docker compose)
  if ! docker compose version >/dev/null 2>&1; then
    if command -v docker-compose >/dev/null 2>&1; then
      COMPOSE=(docker-compose)
    else
      echo "ERROR: docker compose not available"
      exit 127
    fi
  fi

  LOCK_FILE="${LOG_DIR}/.cron_docker_all.lock"
  if command -v flock >/dev/null 2>&1; then
    exec 9>"${LOCK_FILE}"
    if ! flock -n 9; then
      echo "ERROR: Another all-clients Docker run is in progress"
      exit 75
    fi
  else
    echo "WARN: flock not found — skipping lock (shared hosting?)"
  fi

  echo "Building Docker image (run after every git pull)..."
  "${COMPOSE[@]}" build seo-reports

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
} >>"${LOG_FILE}" 2>&1

STATUS=$?
if [[ "${STATUS}" -eq 0 ]]; then
  echo "OK — rapport SEO terminé. Détails: ${LOG_FILE}"
else
  echo "ERREUR (code ${STATUS}) — voir le log: ${LOG_FILE}"
fi
exit "${STATUS}"
