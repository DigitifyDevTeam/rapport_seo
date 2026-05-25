#!/usr/bin/env bash
# GMB sessions must be prepared on Windows (same as Origincbd), not on the VPS.
#
# Usage:
#   ./scripts/docker_gmb_prepare.sh deepcleaning
#
# This only prints instructions. Run prepare on your PC, then copy:
#   outputs/_sessions/gmb-<client>.json  →  same path on the VPS
set -euo pipefail
CLIENT="${1:?client id (e.g. deepcleaning)}"
cat <<EOF
GMB prepare for "${CLIENT}" — use Windows (not the VPS browser)

  python scripts/clients/${CLIENT}/gmb_ui_prepare.py

In the browser:
  1) Sign in to Google
  2) Open the brand fiche → « interactions avec les clients » → Performance
  3) Press ENTER only when the saved URL contains #mpd=

Copy to the VPS (FileZilla):
  outputs/_sessions/gmb-${CLIENT}.json

Verify on the server:
  docker compose run --rm --no-TTY seo-reports python scripts/check_gmb_vps_sessions.py

Monthly cron then captures GMB headless (no server login).
EOF
