#!/usr/bin/env bash
# Refresh Microsoft Clarity cookies (sliding window) without generating a report.
#
#   bash scripts/clarity_ui_keepalive.sh
#
# Microsoft will not honour a longer expiry in the JSON. This script opens the
# dashboard with the saved cookies and re-saves ESTSAUTH* after a live hit so
# a KMSI session stays valid between monthly crons.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=scripts/docker_compose_user.sh
source "${ROOT}/scripts/docker_compose_user.sh"

SESSIONS="${ROOT}/outputs/_sessions"
SESSION_HOST=""
for candidate in \
  clarity-shared.json \
  clarity-digitify.json \
  clarity-deepcleaning.json \
  clarity-origincbd.json \
  clarity-guivarche.json \
  clarity-cchabitat.json
do
  if [[ -f "${SESSIONS}/${candidate}" ]]; then
    SESSION_HOST="${SESSIONS}/${candidate}"
    SESSION_APP="/app/outputs/_sessions/${candidate}"
    break
  fi
done

if [[ -z "${SESSION_HOST:-}" ]]; then
  echo "ERROR: no Clarity session JSON in ${SESSIONS}"
  echo "Log in first: bash scripts/clarity_ui_prepare_vnc_client.sh digitify"
  exit 2
fi

PROJECT_ID="${CLARITY_KEEPALIVE_PROJECT_ID:-k23l3ye7zj}"

echo "Clarity keep-alive using ${SESSION_HOST} (project ${PROJECT_ID})"
docker compose run --rm --no-TTY "${DOCKER_RUN_USER_ARGS[@]}" seo-reports \
  node /app/scripts/clarity_ui_extract.js \
    --session "${SESSION_APP}" \
    --project-id "${PROJECT_ID}" \
    --keepalive \
    --auto
