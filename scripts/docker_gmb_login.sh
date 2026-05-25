#!/usr/bin/env bash
# Optional: refresh GMB Playwright session on the VPS (interactive).
# Normal monthly runs use the Performance API fallback when the browser fails.
# Usage: ./scripts/docker_gmb_login.sh deepcleaning
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:?client id (origincbd, deepcleaning, digitify, cchabitat)}"
SESSION="outputs/_sessions/gmb-${CLIENT}.json"
mkdir -p outputs/_sessions
echo "Opening browser in Docker — log in to Google, open Performance (#mpd= in URL), then press ENTER."
docker compose --profile tools run --rm -it \
  --entrypoint /app/docker-entrypoint.sh \
  seo-tools \
  python scripts/gmb_ui_login.py \
  --out "/app/${SESSION}" \
  --client-hint "${CLIENT}" \
  --channel chromium
