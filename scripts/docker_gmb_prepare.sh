#!/usr/bin/env bash
# GMB session capture on the VPS (same IP as monthly cron).
#
# Usage (SSH with -t):
#   ./scripts/docker_gmb_prepare.sh deepcleaning
#
# Uses a virtual display (Xvfb) — you will not see the browser window.
# Complete Google sign-in on your phone if prompted; then follow terminal text.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:?client id (e.g. deepcleaning)}"
PREPARE="scripts/clients/${CLIENT}/gmb_ui_prepare.py"
if [[ ! -f "${ROOT}/${PREPARE}" ]]; then
  echo "No prepare script: ${PREPARE}" >&2
  exit 1
fi
docker compose build seo-reports
echo "Starting GMB prepare for ${CLIENT} (virtual display via Xvfb)..."
docker compose run --rm -it \
  -e SEO_REPORT_DOCKER=1 \
  -e SEO_REPORT_GMB_NO_PROFILE=0 \
  -e SEO_REPORT_BROWSER_CHANNEL=chromium \
  seo-reports \
  bash -lc "xvfb-run -a --server-args='-screen 0 1920x1080x24' python ${PREPARE}"
