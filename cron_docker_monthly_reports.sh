#!/usr/bin/env bash
# =============================================================================
# VPS cron entry point — runs the full pipeline inside Docker.
#
# Point your VPS cron / scheduled task at this file:
#   /home/USER/public_html/rapport_seo/cron_docker_monthly_reports.sh
#
# Optional:
#   ./cron_docker_monthly_reports.sh --month 2026-04
#
# Requires: Docker + Docker Compose v2 on the server.
# Logs: logs/cron_docker_YYYY-MM-DD_HHMMSS.log
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}" "${ROOT}/outputs" "${ROOT}/secrets"
LOG_FILE="${LOG_DIR}/cron_docker_$(date +%Y-%m-%d_%H%M%S).log"
exec >>"${LOG_FILE}" 2>&1

echo "=== SEO Docker pipeline started at $(date -Iseconds) ==="
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

COMPOSE=(docker compose)
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    echo "ERROR: docker compose not available"
    exit 127
  fi
fi

LOCK_FILE="${LOG_DIR}/.cron_docker.lock"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "ERROR: Another Docker report run is in progress"
  exit 75
fi

echo "Building image (rebuild after git pull)..."
"${COMPOSE[@]}" build seo-reports

echo "Ensuring PowerPoint template is up to date (backlinks / no merci slide)..."
"${COMPOSE[@]}" run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
  python scripts/build_template.py --force-if-stale

set +e
"${COMPOSE[@]}" run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
  python -m src.pipeline.monthly_job "$@"
EXIT_CODE=$?
set -e

if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo "=== Docker pipeline finished OK at $(date -Iseconds) ==="
else
  echo "=== Docker pipeline FAILED (exit ${EXIT_CODE}) at $(date -Iseconds) ==="
fi
exit "${EXIT_CODE}"
