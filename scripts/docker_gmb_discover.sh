#!/usr/bin/env bash
# Discover GMB location id inside Docker (run once per client).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
CLIENT="${1:-cchabitat}"
docker compose run --rm --no-TTY seo-reports \
  python "scripts/clients/${CLIENT}/discover_gmb_location.py"
