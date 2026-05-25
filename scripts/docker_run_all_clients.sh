#!/usr/bin/env bash
# Run all production clients in Docker, then upload each PPTX to Google Drive.
#
# Cron / monthly task — call with NO month (auto YYYY-MM from today + .env):
#   ./scripts/docker_run_all_clients.sh
#
# Manual override for a specific report month:
#   ./scripts/docker_run_all_clients.sh 2026-04
#   ./scripts/docker_run_all_clients.sh --month 2026-04
#
# Auto month uses Period.for_scheduled_run() (same as monthly_job): on or after
# SEO_REPORT_SCHEDULE_DAY / REPORT_CYCLE_DAY (default 26) → current calendar month;
# before that day → previous calendar month.
#
# Per client: ./scripts/docker_run_client.sh <id> <month>, then Drive upload under
# GOOGLE_DRIVE_FOLDER_ID (e.g. rapport_seo) → <project name> → YYYY-MM → .pptx
#
# Requires .env with GOOGLE_DRIVE_FOLDER_ID and Drive credentials (OAuth or SA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

MONTH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --month)
      MONTH="${2:?--month requires YYYY-MM}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      if [[ -z "${MONTH}" ]]; then
        MONTH="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        exit 2
      fi
      ;;
  esac
done

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: Missing ${ROOT}/.env" >&2
  exit 1
fi

if [[ -z "${MONTH}" ]]; then
  MONTH="$(docker compose run --rm --no-TTY seo-reports python -c "
from src.periods import Period
print(Period.for_scheduled_run().label)
")"
  echo "Reporting month (auto): ${MONTH}"
else
  echo "Reporting month (manual): ${MONTH}"
fi

echo "=== Run all production clients (month=${MONTH}) ==="

read -r -a CLIENTS <<< "$(
  docker compose run --rm --no-TTY seo-reports python -c "
from src.config import load_production_clients
print(' '.join(c.id for c in load_production_clients()))
"
)"

if [[ "${#CLIENTS[@]}" -eq 0 ]]; then
  echo "ERROR: No production clients in config/clients.yaml" >&2
  exit 1
fi

echo "Clients: ${CLIENTS[*]}"

SKIP_GMB_CHECK="$(grep -E '^SEO_REPORT_SKIP_GMB_SESSION_CHECK=' "${ROOT}/.env" 2>/dev/null \
  | cut -d= -f2- | tr -d '\r' || true)"
if [[ "${SKIP_GMB_CHECK,,}" != "1" && "${SKIP_GMB_CHECK,,}" != "true" && "${SKIP_GMB_CHECK,,}" != "yes" ]]; then
  echo ""
  echo "=== GMB session preflight (VPS automated capture) ==="
  if ! docker compose run --rm --no-TTY seo-reports \
    python scripts/check_gmb_vps_sessions.py; then
    echo "ERROR: Fix GMB sessions before cron can run unattended." >&2
    echo "  ./scripts/docker_gmb_prepare.sh <client_id>" >&2
    exit 1
  fi
fi

FAILURES=0
for CLIENT in "${CLIENTS[@]}"; do
  echo ""
  echo "=== ${CLIENT} ==="
  if ! "${ROOT}/scripts/docker_run_client.sh" "${CLIENT}" "${MONTH}"; then
    echo "ERROR: Report failed for ${CLIENT}" >&2
    FAILURES=$((FAILURES + 1))
    continue
  fi

  if ! docker compose run --rm --no-TTY seo-reports \
    python scripts/upload_report_to_drive.py --client "${CLIENT}" --month "${MONTH}"; then
    echo "ERROR: Drive upload failed for ${CLIENT}" >&2
    FAILURES=$((FAILURES + 1))
  fi
done

if [[ "${FAILURES}" -gt 0 ]]; then
  echo ""
  echo "=== Finished with ${FAILURES} failure(s) ===" >&2
  exit 1
fi

echo ""
echo "=== All clients OK (reports + Drive upload) ==="
