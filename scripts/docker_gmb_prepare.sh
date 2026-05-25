#!/usr/bin/env bash
# Interactive GMB login on the VPS (same IP as Docker reports).
# Usage: ./scripts/docker_gmb_prepare.sh deepcleaning
#
# Requires SSH with TTY (-t). Sign in + open Performance, then press ENTER.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:?client id (e.g. deepcleaning)}"
PREPARE="${ROOT}/scripts/clients/${CLIENT}/gmb_ui_prepare.py"
if [[ ! -f "${PREPARE}" ]]; then
  echo "No prepare script: ${PREPARE}" >&2
  exit 1
fi
docker compose build seo-reports
docker compose --profile tools run --rm -it seo-tools \
  python "scripts/clients/${CLIENT}/gmb_ui_prepare.py"
